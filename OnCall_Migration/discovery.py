#!/usr/bin/env python3
"""
Export discoverable Splunk On-Call (VictorOps) configuration from the source org to JSON.

Usage:
    cp .env.example .env   # set SOURCE_SPLUNK_ONCALL_API_ID, API_KEY, ORG_SLUG
    python3 discovery.py
    python3 discovery.py -h
    python3 discovery.py --inventory inventory

    # uv (with project .venv):
    uv run python3 discovery.py

    # uv (ephemeral, no venv):
    uv run --with requests python3 discovery.py

Output: inventory/*.json, inventory_summary.md, discovery_metadata.json

Next steps: validate_inventory.py, generate_remapping.py, validate_apply.py, apply.py
"""

import argparse
import sys

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export discoverable Splunk On-Call config from the source org to JSON.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--inventory", default="inventory", help="Output directory for inventory JSON.")
    return parser


if __name__ == "__main__" and any(flag in sys.argv for flag in ("-h", "--help")):
    _build_arg_parser().parse_args()

import itertools
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.env_loader import PROJECT_ROOT, load_dotenv
from utils.exceptions import ApiError, NetworkError
from utils.summary_reporter import SummaryReporter
from utils.migration_types import InventoryCounts
from utils.rate_limiter import RateLimiter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


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
                raise NetworkError(f"Failed to fetch {url}: {exc}") from exc

            if resp.status_code == 404:
                msg = f"Endpoint not found (404): {url}"
                if required:
                    log.critical(msg)
                    raise ApiError(msg)
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
    def __init__(
        self,
        client: VictorOpsClient,
        output_dir: Path,
        reporter: Optional[SummaryReporter] = None,
    ):
        self.client = client
        self.output_dir = output_dir
        self.inventory_counts: InventoryCounts = {}
        self.reporter = reporter or SummaryReporter(output_dir, client.org_slug, self.inventory_counts)

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

        users, teams = self._process_global_entities()
        self._process_user_scoped_entities(users)
        policies_list = self._process_team_scoped_entities(teams)
        if policies_list is not None:
            self._process_policy_details(policies_list)

        elapsed = time.monotonic() - start_time
        self._finalize_run(elapsed)
        return self.inventory_counts

    def _process_global_entities(self) -> Tuple[List[Any], List[Any]]:
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
        return users, teams

    def _process_user_scoped_entities(self, users: List[Any]) -> None:
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
            return

        log.warning("[Phase 2/4] No users found — skipping user-scoped entities.")
        self.inventory_counts["contact_methods_inventory"] = 0
        self.inventory_counts["paging_policies_inventory"] = 0

    def _process_team_scoped_entities(self, teams: List[Any]) -> Optional[List[Any]]:
        if not teams:
            log.warning("[Phase 3/4] No teams found — skipping team-scoped entities.")
            self.inventory_counts["team_members_inventory"] = 0
            self.inventory_counts["team_admins_inventory"] = 0
            self.inventory_counts["rotation_definitions_inventory"] = 0
            self.inventory_counts["escalation_policies_inventory"] = 0
            self.inventory_counts["schedules_inventory"] = 0
            self.inventory_counts["scheduled_overrides_inventory"] = 0
            self.inventory_counts["escalation_policy_details_inventory"] = 0
            return None

        log.info(f"\n[Phase 3/4] Fetching team-scoped entities ({len(teams)} teams)...")
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

        log.info("Fetching Escalation Policies summaries...")
        policies_raw = self.client.get("policies", required=True)
        policies_list = self.extract_list(policies_raw, "policies")

        grouped_policies = {}
        for policy in policies_list:
            tslug = (policy.get("team") or {}).get("slug")
            if tslug:
                grouped_policies.setdefault(tslug, []).append(policy)

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
        return policies_list

    def _process_policy_details(self, policies_list: List[Any]) -> None:
        log.info("\n[Phase 4/4] Fetching escalation policy details...")
        unique_slugs = {
            policy.get("policy", {}).get("slug")
            for policy in policies_list
            if policy.get("policy", {}).get("slug")
        }
        policy_slugs = sorted(unique_slugs)

        log.info(f"Fetching {len(policy_slugs)} unique policy details...")
        policy_details = self.fetch_per_entity_concurrent(
            [{"slug": slug} for slug in policy_slugs], "slug", lambda slug: f"policies/{slug}", "policy"
        )
        self.save_json("escalation_policy_details_inventory", policy_details)
        self.inventory_counts["escalation_policy_details_inventory"] = len(policy_details)

    def _finalize_run(self, elapsed: float) -> None:
        self.save_metadata(elapsed)
        self.reporter.write_summary(elapsed)

        minutes, seconds = divmod(int(elapsed), 60)
        log.info("=" * 60)
        log.info(f"Discovery complete in {minutes}m {seconds:02d}s.")
        log.info("=" * 60)

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


def main(argv: Optional[List[str]] = None) -> None:
    args = _build_arg_parser().parse_args(argv)

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
    pipeline = DiscoveryPipeline(client, Path(args.inventory))
    pipeline.run()

if __name__ == "__main__":
    main()
