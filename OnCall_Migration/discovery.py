#!/usr/bin/env python3
"""
Author: Brandon Blinderman
Date: 07/16/2026

Splunk On-Call (VictorOps) Discovery Script.
Exports all discoverable configurations from the SOURCE organization to versioned JSON files.

Usage:
    cp .env.example .env   # set SOURCE_SPLUNK_ONCALL_API_ID, API_KEY, ORG_SLUG
    python3 discovery.py

    # Or via shell export (takes precedence over .env):
    export SOURCE_SPLUNK_ONCALL_API_ID="your-api-id"
    export SOURCE_SPLUNK_ONCALL_API_KEY="your-api-key"
    export SOURCE_SPLUNK_ONCALL_ORG_SLUG="your-org-slug"
    python3 discovery.py

Output: inventory/*.json, inventory_summary.md, discovery_metadata.json

Next steps: validate_inventory.py → generate_remapping.py → validate_apply.py → apply.py
"""

import itertools
import json
import logging
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from env_loader import PROJECT_ROOT, load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

class RateLimiter:
    """Thread-safe rate limiter to strictly adhere to VictorOps 2 req/sec limits."""
    def __init__(self, rate_hz: float):
        self.delay = 1.0 / rate_hz
        self.last_call = 0.0
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_call
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
            self.last_call = time.monotonic()

class VictorOpsClient:
    """Encapsulates API session, base URLs, rate limiting, and generic fetching."""
    def __init__(self, api_id: str, api_key: str, org_slug: str):
        self.api_id = api_id
        self.api_key = api_key
        self.org_slug = org_slug
        self.base_v1 = "https://api.victorops.com/api-public/v1"
        self.base_v2 = "https://api.victorops.com/api-public/v2"

        self.session = requests.Session()
        retries = Retry(total=6, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
        self.session.mount("https://", HTTPAdapter(max_retries=retries))
        self.session.headers.update({
            "X-VO-Api-Id": self.api_id,
            "X-VO-Api-Key": self.api_key,
            "Accept": "application/json",
        })
        self.rate_limiter = RateLimiter(rate_hz=2.0) # max 2 req/sec

    def get(self, endpoint: str, params: Optional[Dict] = None, use_v2: bool = False, paginate: bool = True, required: bool = False) -> Any:
        base_url = self.base_v2 if use_v2 else self.base_v1
        url = endpoint if endpoint.startswith("http") else f"{base_url}/{endpoint.lstrip('/')}"

        merged = []
        is_list_response = False
        current_params = params.copy() if params else {}
        if paginate:
            current_params.setdefault("limit", 100)
            current_params.setdefault("offset", 0)

        while url:
            self.rate_limiter.wait()
            try:
                resp = self.session.get(url, params=current_params, timeout=30)
            except requests.RequestException as exc:
                log.error(f"Network Error: {url} - {exc}")
                raise RuntimeError(f"Failed to fetch {url}: {exc}") from exc

            if resp.status_code == 404:
                msg = f"Endpoint not found (404): {url}"
                if required:
                    log.critical(msg)
                    raise RuntimeError(msg)
                log.warning(f"Not Found (404) for {url}, skipping.")
                return None

            if resp.status_code != 200:
                log.error(f"HTTP {resp.status_code} {url} - {resp.text[:200]}")
                resp.raise_for_status()

            data = resp.json()

            if isinstance(data, list):
                if not paginate: return data
                is_list_response = True
                merged.extend(data)
                break

            if isinstance(data, dict):
                list_keys = [k for k, v in data.items() if isinstance(v, list)]
                if list_keys and paginate:
                    if len(list_keys) > 1:
                        # Multi-list dict (e.g. contact-methods) returned intact to prevent data loss
                        return data

                    is_list_response = True
                    primary_key = next(
                        (k for k in list_keys if data[k] and isinstance(data[k][0], dict)),
                        list_keys[0],
                    )
                    page_items = data[primary_key]
                    merged.extend(page_items)

                    next_url = data.get("nextPage") or data.get("next_page") or data.get("next")
                    if next_url:
                        url = next_url if next_url.startswith("http") else f"{base_url}/{next_url.lstrip('/')}"
                        current_params = {}
                        continue

                    limit = current_params.get("limit", 100)
                    if page_items and len(page_items) == limit and isinstance(page_items[0], dict):
                        current_params["offset"] = current_params.get("offset", 0) + limit
                        continue
                    break
                return data

            url = None

        return merged if is_list_response else data


class DiscoveryPipeline:
    """Orchestrates the data extraction logic using VictorOpsClient."""
    def __init__(self, client: VictorOpsClient, output_dir: Path):
        self.client = client
        self.output_dir = output_dir
        self.inventory_counts = {}

    def save_json(self, name: str, data: Any):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"{name}.json"

        # Atomic writes prevent corrupted half-states
        temp_path = path.with_suffix('.tmp')
        temp_path.write_text(json.dumps(data, indent=2))
        temp_path.replace(path)

        if isinstance(data, list):
            log.info(f"  -> Saved {len(data)} items to {path.name}")
        elif isinstance(data, dict):
            log.info(f"  -> Saved {len(data)} entities to {path.name}")
        else:
            log.info(f"  -> Saved to {path.name}")

    def extract_list(self, data: Any, key: str = "") -> List[Any]:
        if data is None: return []
        if isinstance(data, list):
            if data and isinstance(data[0], list):
                return list(itertools.chain.from_iterable(data))
            return data
        if isinstance(data, dict):
            return data.get(key, []) or []
        return []

    def parse_timestamp(self, ts: str) -> Optional[datetime]:
        if not ts: return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            log.warning(f"Invalid timestamp format: {ts}")
            return None

    def is_override_active(self, override: Dict, now: datetime) -> bool:
        end_ts = override.get("end")
        if not end_ts: return True
        end_dt = self.parse_timestamp(end_ts)
        if not end_dt:
            log.warning(f"Skip Override {override.get('publicId')}: treating invalid end timestamp as inactive.")
            return False
        return end_dt > now

    def fetch_per_entity_concurrent(
        self,
        entities: List[Dict],
        id_key: str,
        endpoint_factory: Callable[[str], str],
        label: str,
        use_v2: bool = False,
        paginate: bool = True,
    ) -> Dict[str, Any]:
        """Concurrent per-entity fetching controlled by thread-safe rate limiter."""
        results = {}
        skipped = 0

        def fetch(entity):
            entity_id = entity.get(id_key)
            if not entity_id:
                return None, None
            data = self.client.get(
                endpoint_factory(entity_id), use_v2=use_v2, paginate=paginate
            )
            return entity_id, data

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(fetch, e): e for e in entities}
            for i, future in enumerate(as_completed(futures), 1):
                entity_id, data = future.result()
                if entity_id:
                    if data is not None:
                        results[entity_id] = data
                    else:
                        log.debug(f"No data for {label} '{entity_id}'")
                else:
                    skipped += 1
                if i % 25 == 0 or i == len(entities):
                    log.info(f"  [{i}/{len(entities)}] {label} fetched")

        if skipped:
            log.warning(f"  -> Skipped {skipped} {label}s with no '{id_key}' identifier.")
        return results

    def get_scheduled_overrides(self) -> Dict[str, List[Any]]:
        log.info("Fetching Scheduled Overrides...")
        now = datetime.now(timezone.utc)
        raw_list = self.extract_list(self.client.get("overrides", required=True), "overrides")

        grouped = {}
        total_active = 0

        for override in raw_list:
            if not isinstance(override, dict): continue
            if not self.is_override_active(override, now): continue

            total_active += 1
            teamslugs = [
                assignment.get("team") for assignment in override.get("assignments", [])
                if isinstance(assignment, dict) and assignment.get("team")
            ]
            if not teamslugs:
                grouped.setdefault("_unassigned", []).append(override)
                continue
            for teamslug in sorted(teamslugs):
                grouped.setdefault(teamslug, []).append(override)

        log.info(f"  -> Override summary: {len(raw_list)} fetched, {total_active} active kept, {len(grouped)} team buckets.")
        return grouped

    def run(self) -> Dict[str, Any]:
        start_time = time.monotonic()
        log.info("=" * 60)
        log.info(f"Splunk On-Call Discovery | Org: {self.client.org_slug}")
        log.info(f"Output directory: {self.output_dir.resolve()}")
        log.info("=" * 60)

        # Phase 1: Global entities
        log.info("[Phase 1/4] Fetching global entities...")
        users = self.extract_list(self.client.get("user", required=True), "users")
        self.save_json("users_inventory", users)
        self.inventory_counts["users_inventory"] = len(users)

        teams = self.extract_list(self.client.get("team", required=True), "teams")
        self.save_json("teams_inventory", teams)
        self.inventory_counts["teams_inventory"] = len(teams)

        routing_keys = self.extract_list(
            self.client.get("org/routing-keys", required=True), "routingKeys"
        )
        self.save_json("routing_keys_inventory", routing_keys)
        self.inventory_counts["routing_keys_inventory"] = len(routing_keys)

        rules_raw = self.client.get("alertRules", required=True)
        rules_list = self.extract_list(rules_raw, "rules")
        rules_list.sort(key=lambda x: x.get("rank", 0))
        self.save_json("alert_rules_inventory", rules_list)
        self.inventory_counts["alert_rules_inventory"] = len(rules_list)

        webhooks = self.extract_list(self.client.get("webhooks", required=True), "webhooks")
        self.save_json("outbound_webhooks_inventory", webhooks)
        self.inventory_counts["outbound_webhooks_inventory"] = len(webhooks)

        self.inventory_counts["integrations_inventory"] = 0

        # Phase 2: User-scoped
        if users:
            log.info(f"\n[Phase 2/4] Fetching user-scoped entities ({len(users)} users)...")
            log.info("Fetching User Contact Methods...")
            contact_methods = self.fetch_per_entity_concurrent(
                users, "username", lambda u: f"user/{u}/contact-methods", "user"
            )
            self.save_json("contact_methods_inventory", contact_methods)
            self.inventory_counts["contact_methods_inventory"] = len(contact_methods)

            log.info("Fetching User Paging Policies...")
            paging_policies = self.fetch_per_entity_concurrent(
                users, "username", lambda u: f"user/{u}/policies", "user"
            )
            self.save_json("paging_policies_inventory", paging_policies)
            self.inventory_counts["paging_policies_inventory"] = len(paging_policies)
        else:
            log.warning("[Phase 2/4] No users found — skipping user-scoped entities.")
            self.inventory_counts["contact_methods_inventory"] = 0
            self.inventory_counts["paging_policies_inventory"] = 0

        # Phase 3: Team-scoped
        if teams:
            log.info(f"\n[Phase 3/4] Fetching team-scoped entities ({len(teams)} teams)...")
            # Fetching Members
            log.info("Fetching Team Members...")
            team_members = self.fetch_per_entity_concurrent(
                teams, "slug", lambda t: f"team/{t}/members", "team"
            )
            self.save_json("team_members_inventory", team_members)
            self.inventory_counts["team_members_inventory"] = len(team_members)

            log.info("Fetching Team Admins...")
            team_admins = self.fetch_per_entity_concurrent(
                teams, "slug", lambda t: f"team/{t}/admins", "team"
            )
            self.save_json("team_admins_inventory", team_admins)
            self.inventory_counts["team_admins_inventory"] = len(team_admins)

            log.info("Fetching Team Rotation Definitions...")
            rotations = self.fetch_per_entity_concurrent(
                teams,
                "slug",
                lambda t: f"team/{t}/rotations",
                "team",
                use_v2=True,
                paginate=False,
            )
            self.save_json("rotation_definitions_inventory", rotations)
            self.inventory_counts["rotation_definitions_inventory"] = len(rotations)

            # Escalation Policies
            log.info("Fetching Escalation Policies summaries...")
            policies_raw = self.client.get("policies", required=True)
            policies_list = self.extract_list(policies_raw, "policies")

            # Grouping Logic
            grouped_policies = {}
            for p in policies_list:
                tslug = (p.get("team") or {}).get("slug")
                if tslug: grouped_policies.setdefault(tslug, []).append(p)

            self.save_json("escalation_policies_inventory", grouped_policies)
            self.inventory_counts["escalation_policies_inventory"] = len(grouped_policies)

            log.info("Fetching On-Call Schedules v2...")
            schedules = self.fetch_per_entity_concurrent(
                teams, "slug", lambda t: f"team/{t}/oncall/schedule", "team", use_v2=True
            )
            self.save_json("schedules_inventory", schedules)
            self.inventory_counts["schedules_inventory"] = len(schedules)

            overrides = self.get_scheduled_overrides()
            self.save_json("scheduled_overrides_inventory", overrides)
            self.inventory_counts["scheduled_overrides_inventory"] = len(overrides)

            log.info(f"\n[Phase 4/4] Fetching escalation policy details...")
            unique_slugs = {
                p.get("policy", {}).get("slug")
                for p in policies_list
                if p.get("policy", {}).get("slug")
            }
            policy_slugs = sorted(unique_slugs)

            log.info(f"Fetching {len(policy_slugs)} unique policy details...")
            policy_details = self.fetch_per_entity_concurrent(
                [{"slug": s} for s in policy_slugs], "slug", lambda s: f"policies/{s}", "policy"
            )
            self.save_json("escalation_policy_details_inventory", policy_details)
            self.inventory_counts["escalation_policy_details_inventory"] = len(policy_details)
        else:
            log.warning("[Phase 3/4] No teams found — skipping team-scoped entities.")
            self.inventory_counts["team_members_inventory"] = 0
            self.inventory_counts["team_admins_inventory"] = 0
            self.inventory_counts["rotation_definitions_inventory"] = 0
            self.inventory_counts["escalation_policies_inventory"] = 0
            self.inventory_counts["schedules_inventory"] = 0
            self.inventory_counts["scheduled_overrides_inventory"] = 0
            self.inventory_counts["escalation_policy_details_inventory"] = 0

        elapsed = time.monotonic() - start_time
        self.save_metadata(elapsed)
        self.save_inventory_summary(elapsed)

        minutes, seconds = divmod(int(elapsed), 60)
        log.info("=" * 60)
        log.info(f"Discovery complete in {minutes}m {seconds:02d}s.")
        log.info("=" * 60)
        return self.inventory_counts

    def save_metadata(self, elapsed_seconds: float):
        files_written = [
            {"name": f"{name}.json", "count": count}
            for name, count in sorted(self.inventory_counts.items())
        ]
        metadata = {
            "org_slug": self.client.org_slug,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "api_version": "v1/v2",
            "elapsed_seconds": round(elapsed_seconds, 1),
            "inventory_counts": self.inventory_counts,
            "files_written": files_written,
            "manual_capture_required": ["integrations", "user_permissions", "sso_settings"],
            "notes": {
                "integrations_inventory": (
                    "Not exported — no public Splunk On-Call API endpoint exists for "
                    "listing integrations. See manual_capture/README.md."
                ),
            }
        }
        self.save_json("discovery_metadata", metadata)

    def _load_inventory_json(self, name: str) -> Any:
        path = self.output_dir / f"{name}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def _format_duration(self, elapsed_seconds: float) -> str:
        minutes, seconds = divmod(int(elapsed_seconds), 60)
        return f"{minutes}m {seconds:02d}s"

    def _team_slug_from_url(self, url: str) -> str:
        if not url:
            return ""
        return url.rstrip("/").split("/")[-1]

    def _rotation_labels(self, rotation_data: Any) -> str:
        if not isinstance(rotation_data, dict):
            return ""
        rotations = rotation_data.get("rotations") or []
        labels = [
            r.get("label", "")
            for r in rotations
            if isinstance(r, dict) and r.get("label")
        ]
        return ", ".join(labels)

    def _md_cell(self, value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    def save_inventory_summary(self, elapsed_seconds: float) -> None:
        """Write a human-readable Markdown catalog from saved inventory JSON."""
        exported_at = datetime.now(timezone.utc).isoformat()
        lines = [
            "# Splunk On-Call Inventory Summary",
            "",
            f"**Org:** {self.client.org_slug}  ",
            f"**Exported:** {exported_at}  ",
            f"**Duration:** {self._format_duration(elapsed_seconds)}",
            "",
            "## Inventory Counts",
            "",
            "| File | Count |",
            "| --- | ---: |",
        ]

        for name, count in sorted(self.inventory_counts.items()):
            lines.append(f"| `{name}.json` | {count} |")

        teams = self._load_inventory_json("teams_inventory") or []
        team_members = self._load_inventory_json("team_members_inventory") or {}
        team_admins = self._load_inventory_json("team_admins_inventory") or {}
        rotations = self._load_inventory_json("rotation_definitions_inventory") or {}
        escalation_policies = self._load_inventory_json("escalation_policies_inventory") or {}

        lines.extend(["", f"## Teams ({len(teams)})", ""])
        if teams:
            lines.extend([
                "| Name | Slug | Members | Admins | Rotations | Escalation Policies |",
                "| --- | --- | ---: | ---: | --- | ---: |",
            ])
            for team in sorted(teams, key=lambda t: (t.get("name") or "").lower()):
                if not isinstance(team, dict):
                    continue
                slug = team.get("slug", "")
                name = team.get("name", "")
                member_count = len(team_members.get(slug, [])) if isinstance(team_members, dict) else 0
                admin_count = len(team_admins.get(slug, [])) if isinstance(team_admins, dict) else 0
                rotation_labels = self._rotation_labels(rotations.get(slug) if isinstance(rotations, dict) else None)
                policy_count = len(escalation_policies.get(slug, [])) if isinstance(escalation_policies, dict) else 0
                lines.append(
                    f"| {self._md_cell(name)} | {self._md_cell(slug)} | {member_count} | "
                    f"{admin_count} | {self._md_cell(rotation_labels)} | {policy_count} |"
                )
        else:
            lines.append("_No teams exported._")

        routing_keys = self._load_inventory_json("routing_keys_inventory") or []
        lines.extend(["", f"## Routing Keys ({len(routing_keys)})", ""])
        if routing_keys:
            lines.extend([
                "| Routing Key | Target Policy | Team Slug |",
                "| --- | --- | --- |",
            ])
            for rk in sorted(routing_keys, key=lambda r: (r.get("routingKey") or "").lower()):
                if not isinstance(rk, dict):
                    continue
                key = rk.get("routingKey", "")
                targets = rk.get("targets") or []
                target = targets[0] if targets and isinstance(targets[0], dict) else {}
                policy_name = target.get("policyName", "")
                team_slug = self._team_slug_from_url(target.get("_teamUrl", ""))
                lines.append(
                    f"| {self._md_cell(key)} | {self._md_cell(policy_name)} | {self._md_cell(team_slug)} |"
                )
        else:
            lines.append("_No routing keys exported._")

        alert_rules = self._load_inventory_json("alert_rules_inventory") or []
        lines.extend(["", f"## Alert Rules ({len(alert_rules)})", ""])
        if alert_rules:
            lines.extend([
                "| Rank | Field | Match | Match Type | Stop |",
                "| ---: | --- | --- | --- | :---: |",
            ])
            for rule in sorted(alert_rules, key=lambda r: r.get("rank", 0)):
                if not isinstance(rule, dict):
                    continue
                lines.append(
                    f"| {rule.get('rank', '')} | {self._md_cell(rule.get('alertField', ''))} | "
                    f"{self._md_cell(rule.get('alertValueMatch', ''))} | "
                    f"{self._md_cell(rule.get('matchType', ''))} | "
                    f"{'Yes' if rule.get('stopFlag') else 'No'} |"
                )
        else:
            lines.append("_No alert rules exported._")

        webhooks = self._load_inventory_json("outbound_webhooks_inventory") or []
        lines.extend(["", f"## Outbound Webhooks ({len(webhooks)})", ""])
        if webhooks:
            lines.extend([
                "| Label | Slug |",
                "| --- | --- |",
            ])
            for wh in webhooks:
                if not isinstance(wh, dict):
                    continue
                lines.append(
                    f"| {self._md_cell(wh.get('label', ''))} | {self._md_cell(wh.get('slug', ''))} |"
                )
        else:
            lines.append("_No outbound webhooks exported._")

        users = self._load_inventory_json("users_inventory") or []
        lines.extend(["", f"## Users ({len(users)})", ""])
        if users:
            lines.extend([
                "| Username | Display Name |",
                "| --- | --- |",
            ])
            for user in sorted(users, key=lambda u: (u.get("username") or "").lower()):
                if not isinstance(user, dict):
                    continue
                lines.append(
                    f"| {self._md_cell(user.get('username', ''))} | "
                    f"{self._md_cell(user.get('displayName', ''))} |"
                )
        else:
            lines.append("_No users exported._")

        overrides = self._load_inventory_json("scheduled_overrides_inventory") or {}
        override_buckets = len(overrides) if isinstance(overrides, dict) else 0
        active_overrides = (
            sum(len(v) for v in overrides.values())
            if isinstance(overrides, dict)
            else 0
        )
        lines.extend([
            "",
            "## Scheduled Overrides",
            "",
            f"- **Team buckets:** {override_buckets}",
            f"- **Active overrides:** {active_overrides}",
            "",
            "## Manual Capture Required",
            "",
            "- integrations",
            "- user_permissions",
            "- sso_settings",
            "",
            "## Notes",
            "",
            "Integrations are not exported via the public API. See "
            "`manual_capture/README.md` for manual capture steps.",
            "",
        ])

        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / "inventory_summary.md"
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text("\n".join(lines))
        temp_path.replace(path)
        log.info("  -> Saved inventory summary to inventory_summary.md")


def main():
    env_path = load_dotenv()
    if env_path:
        log.info(f"Loaded environment from {env_path}")
    else:
        log.warning(f"No .env file found at {PROJECT_ROOT / '.env'}")

    api_id = os.getenv("SOURCE_SPLUNK_ONCALL_API_ID")
    api_key = os.getenv("SOURCE_SPLUNK_ONCALL_API_KEY")
    org_slug = os.getenv("SOURCE_SPLUNK_ONCALL_ORG_SLUG")

    if not all([api_id, api_key, org_slug]):
        log.critical("Missing required environment variables. Set SOURCE_SPLUNK_ONCALL_API_ID, SOURCE_SPLUNK_ONCALL_API_KEY, SOURCE_SPLUNK_ONCALL_ORG_SLUG.")
        sys.exit(1)

    client = VictorOpsClient(api_id, api_key, org_slug)
    pipeline = DiscoveryPipeline(client, Path("inventory"))
    pipeline.run()

if __name__ == "__main__":
    main()
