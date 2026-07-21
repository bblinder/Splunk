#!/usr/bin/env python3
"""
Apply Splunk On-Call inventory to a target org using remapping.json.

Dry-run by default. Pass --apply to execute writes.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from env_loader import PROJECT_ROOT, load_dotenv
from utils import RateLimiter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


class RemappingContext:
    def __init__(self, remapping: Dict[str, Dict[str, Any]]):
        self.remapping = remapping

    def map_value(self, category: str, source: str) -> Optional[str]:
        mappings = self.remapping.get(category, {})
        if source not in mappings:
            return source
        target = mappings[source]
        if target is None:
            return None
        return str(target)

    def is_skipped(self, category: str, source: str) -> bool:
        mappings = self.remapping.get(category, {})
        return source in mappings and mappings[source] is None


class ApplyClient:
    def __init__(self, api_id: str, api_key: str, org_slug: str, dry_run: bool = True):
        self.org_slug = org_slug
        self.dry_run = dry_run
        self.base_v1 = "https://api.victorops.com/api-public/v1"
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET", "POST"])
        self.session.mount("https://", HTTPAdapter(max_retries=retries))
        self.session.headers.update(
            {
                "X-VO-Api-Id": api_id,
                "X-VO-Api-Key": api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )
        self.rate_limiter = RateLimiter()

    def get(self, endpoint: str, allow_404: bool = False) -> Tuple[Optional[Any], int]:
        url = f"{self.base_v1}/{endpoint.lstrip('/')}"
        self.rate_limiter.wait()
        if self.dry_run and not allow_404:
            log.debug(f"DRY-RUN GET {url}")
        resp = self.session.get(url, timeout=30)
        if resp.status_code == 404 and allow_404:
            return None, 404
        if resp.status_code != 200:
            log.error(f"GET {url} -> {resp.status_code}: {resp.text[:200]}")
            return None, resp.status_code
        return resp.json(), resp.status_code

    def post(self, endpoint: str, payload: Dict[str, Any]) -> Tuple[Optional[Any], int]:
        url = f"{self.base_v1}/{endpoint.lstrip('/')}"
        self.rate_limiter.wait()
        if self.dry_run:
            log.info(f"DRY-RUN POST {url}")
            return {"dry_run": True, "endpoint": endpoint, "payload": payload}, 200
        resp = self.session.post(url, json=payload, timeout=30)
        if resp.status_code not in (200, 201):
            log.error(f"POST {url} -> {resp.status_code}: {resp.text[:200]}")
            return None, resp.status_code
        try:
            return resp.json(), resp.status_code
        except ValueError:
            return {}, resp.status_code


class ApplyPipeline:
    def __init__(
        self,
        client: ApplyClient,
        inventory_dir: Path,
        remapping: RemappingContext,
        report_path: Path,
    ):
        self.client = client
        self.inventory_dir = inventory_dir
        self.remapping = remapping
        self.report_path = report_path
        self.team_slug_map: Dict[str, str] = {}
        self.policy_slug_map: Dict[str, str] = {}
        self.rtg_slug_map: Dict[str, str] = {}
        self.rtg_label_by_source_slug: Dict[str, str] = {}
        self.policy_team_map: Dict[str, str] = {}
        self.stats: Dict[str, Dict[str, int]] = {}

    def _load_json(self, name: str) -> Any:
        path = self.inventory_dir / f"{name}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def _bump(self, step: str, outcome: str) -> None:
        self.stats.setdefault(step, {"created": 0, "skipped": 0, "failed": 0, "warned": 0})
        self.stats[step][outcome] += 1

    def run(self) -> Dict[str, Any]:
        self._index_policy_metadata()
        self._index_rotation_group_labels()
        steps: List[Tuple[str, Callable[[], None]]] = [
            ("users", self.apply_users),
            ("teams", self.apply_teams),
            ("members", self.apply_members),
            ("admins", self.apply_admins),
            ("rotations", self.apply_rotations),
            ("escalation_policies", self.apply_escalation_policies),
            ("routing_keys", self.apply_routing_keys),
            ("alert_rules", self.apply_alert_rules),
        ]
        self._run_steps(steps)
        return self._write_report()

    def _run_steps(self, steps: List[Tuple[str, Callable[[], None]]]) -> None:
        for name, func in steps:
            log.info("=" * 60)
            log.info(f"Apply step: {name}")
            func()

    def _write_report(self) -> Dict[str, Any]:
        report = {
            "org_slug": self.client.org_slug,
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "dry_run": self.client.dry_run,
            "stats": self.stats,
            "slug_maps": {
                "teams": self.team_slug_map,
                "escalation_policies": self.policy_slug_map,
                "rotation_groups": self.rtg_slug_map,
            },
        }
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(json.dumps(report, indent=2))
        log.info(f"Apply report written to {self.report_path}")
        return report

    def _index_policy_metadata(self) -> None:
        grouped = self._load_json("escalation_policies_inventory") or {}
        if not isinstance(grouped, dict):
            return
        for team_slug, policies in grouped.items():
            for entry in policies:
                policy = entry.get("policy", {})
                slug = policy.get("slug")
                if slug:
                    self.policy_team_map[slug] = team_slug

    def _index_rotation_group_labels(self) -> None:
        details = self._load_json("escalation_policy_details_inventory") or {}
        if not isinstance(details, dict):
            return
        for _policy_slug, steps in details.items():
            if not isinstance(steps, list):
                continue
            for step in steps:
                for entry in step.get("entries", []):
                    if entry.get("executionType") not in (
                        "rotation_group",
                        "rotation_group_next",
                        "rotation_group_previous",
                    ):
                        continue
                    rg = entry.get("rotationGroup", {})
                    slug = rg.get("slug")
                    label = rg.get("label")
                    if slug and label:
                        self.rtg_label_by_source_slug[slug] = label

    def apply_users(self) -> None:
        users = self._load_json("users_inventory") or []
        for user in users:
            if not isinstance(user, dict):
                continue
            source_username = user.get("username")
            if not source_username or self.remapping.is_skipped("users", source_username):
                self._bump("users", "skipped")
                continue
            target_username = self.remapping.map_value("users", source_username)
            existing, status = self.client.get(f"user/{target_username}", allow_404=True)
            if status == 200 and existing:
                log.info(f"  SKIP user exists: {target_username}")
                self._bump("users", "skipped")
                continue
            payload = {
                "firstName": user.get("firstName", ""),
                "lastName": user.get("lastName", ""),
                "username": target_username,
                "email": user.get("email", f"{target_username}@example.com"),
            }
            result, code = self.client.post("user", payload)
            if code == 200 and result is not None:
                self._bump("users", "created")
            else:
                self._bump("users", "failed")

    def _list_teams(self) -> List[Dict[str, Any]]:
        data, status = self.client.get("team", allow_404=True)
        if status != 200:
            return []
        if isinstance(data, list):
            return [t for t in data if isinstance(t, dict)]
        if isinstance(data, dict):
            teams = data.get("teams")
            if isinstance(teams, list):
                return [t for t in teams if isinstance(t, dict)]
        return []

    def apply_teams(self) -> None:
        teams = self._load_json("teams_inventory") or []
        existing_by_name = {t.get("name"): t.get("slug") for t in self._list_teams() if t.get("name")}

        for team in teams:
            if not isinstance(team, dict):
                continue
            source_slug = team.get("slug")
            name = team.get("name")
            if not source_slug or not name or self.remapping.is_skipped("teams", source_slug):
                self._bump("teams", "skipped")
                continue
            if name in existing_by_name:
                self.team_slug_map[source_slug] = existing_by_name[name]
                log.info(f"  SKIP team exists: {name} -> {existing_by_name[name]}")
                self._bump("teams", "skipped")
                continue
            payload = {"name": name}
            if team.get("description"):
                payload["description"] = team["description"]
            result, code = self.client.post("team", payload)
            if code == 200 and result:
                target_slug = result.get("slug", source_slug)
                self.team_slug_map[source_slug] = target_slug
                existing_by_name[name] = target_slug
                self._bump("teams", "created")
            else:
                self._bump("teams", "failed")

    def _target_team_slug(self, source_slug: str) -> Optional[str]:
        if self.remapping.is_skipped("teams", source_slug):
            return None
        return self.team_slug_map.get(source_slug, self.remapping.map_value("teams", source_slug))

    def apply_members(self) -> None:
        members_by_team = self._load_json("team_members_inventory") or {}
        if not isinstance(members_by_team, dict):
            return
        for source_team, members in members_by_team.items():
            target_team = self._target_team_slug(source_team)
            if not target_team:
                continue
            for member in members:
                if not isinstance(member, dict):
                    continue
                source_user = member.get("username")
                if not source_user or self.remapping.is_skipped("users", source_user):
                    self._bump("members", "skipped")
                    continue
                target_user = self.remapping.map_value("users", source_user)
                team_members, status = self.client.get(f"team/{target_team}/members", allow_404=True)
                if status == 200 and isinstance(team_members, dict):
                    current = {m.get("username") for m in team_members.get("members", []) if isinstance(m, dict)}
                    if target_user in current:
                        self._bump("members", "skipped")
                        continue
                result, code = self.client.post(f"team/{target_team}/members", {"username": target_user})
                if code == 200 and result is not None:
                    self._bump("members", "created")
                else:
                    self._bump("members", "failed")

    def apply_admins(self) -> None:
        """Team admin assignment has no public POST endpoint — record for manual follow-up."""
        admins_by_team = self._load_json("team_admins_inventory") or {}
        if not isinstance(admins_by_team, dict):
            return
        for source_team, admins in admins_by_team.items():
            if self.remapping.is_skipped("teams", source_team):
                continue
            if not admins:
                continue
            log.warning(
                f"  Team admins for '{source_team}' cannot be applied via API — configure in target UI."
            )
            self._bump("admins", "warned")

    def _iso_to_epoch_ms(self, value: Any) -> int:
        if isinstance(value, (int, float)):
            return int(value)
        if not isinstance(value, str) or not value:
            return 0
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return int(dt.timestamp() * 1000)
        except ValueError:
            return 0

    def _build_rotation_payload(self, rotation: Dict[str, Any]) -> Dict[str, Any]:
        shifts_out = []
        for shift in rotation.get("shifts", []):
            if not isinstance(shift, dict):
                continue
            usernames = []
            for member in shift.get("shiftMembers", []):
                if not isinstance(member, dict):
                    continue
                source_user = member.get("username")
                if source_user and not self.remapping.is_skipped("users", source_user):
                    usernames.append(self.remapping.map_value("users", source_user))
            shift_payload = {
                "label": shift.get("label", "shift"),
                "timezone": shift.get("timezone", "UTC"),
                "start": self._iso_to_epoch_ms(shift.get("start")),
                "duration": min(int(shift.get("duration", 7)), 90),
                "shifttype": shift.get("shifttype", "std"),
                "mask": shift.get("mask", {}),
            }
            if shift.get("mask2"):
                shift_payload["mask2"] = shift["mask2"]
            if shift.get("mask3"):
                shift_payload["mask3"] = shift["mask3"]
            if usernames:
                shift_payload["usernames"] = usernames
            shifts_out.append(shift_payload)
        return {"label": rotation.get("label", "rotation"), "shifts": shifts_out}

    def _refresh_rtg_map_for_team(self, source_team: str, target_team: str) -> None:
        data, status = self.client.get(f"teams/{target_team}/rotations", allow_404=True)
        if status != 200 or not isinstance(data, dict):
            return
        label_to_target = {
            g.get("label"): g.get("slug")
            for g in data.get("rotationGroups", [])
            if isinstance(g, dict) and g.get("label") and g.get("slug")
        }
        details = self._load_json("escalation_policy_details_inventory") or {}
        for policy_slug, steps in (details or {}).items():
            if self.policy_team_map.get(policy_slug) != source_team:
                continue
            for step in steps or []:
                for entry in step.get("entries", []):
                    rg = entry.get("rotationGroup", {})
                    source_rtg = rg.get("slug")
                    source_label = rg.get("label")
                    if source_rtg and source_label and source_label in label_to_target:
                        self.rtg_slug_map[source_rtg] = label_to_target[source_label]

    def apply_rotations(self) -> None:
        rotations_by_team = self._load_json("rotation_definitions_inventory") or {}
        if not isinstance(rotations_by_team, dict):
            return

        for source_team, payload in rotations_by_team.items():
            target_team = self._target_team_slug(source_team)
            if not target_team or not isinstance(payload, dict):
                continue
            for rotation in payload.get("rotations", []):
                if not isinstance(rotation, dict):
                    continue
                label = rotation.get("label", "")
                existing, status = self.client.get(f"teams/{target_team}/rotations", allow_404=True)
                if status == 200 and isinstance(existing, dict):
                    labels = {g.get("label") for g in existing.get("rotationGroups", []) if isinstance(g, dict)}
                    if label in labels:
                        self._bump("rotations", "skipped")
                        self._refresh_rtg_map_for_team(source_team, target_team)
                        continue
                body = self._build_rotation_payload(rotation)
                result, code = self.client.post(f"teams/{target_team}/rotations", body)
                if code == 200 and result is not None:
                    self._bump("rotations", "created")
                else:
                    self._bump("rotations", "failed")
            self._refresh_rtg_map_for_team(source_team, target_team)

    def _transform_policy_entry(self, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        execution_type = entry.get("executionType")
        if execution_type == "webhook":
            log.warning("  Skipping webhook escalation entry (outbound webhooks are deferred).")
            self._bump("escalation_policies", "warned")
            return None
        transformed: Dict[str, Any] = {"executionType": execution_type}
        if execution_type in ("rotation_group", "rotation_group_next", "rotation_group_previous"):
            rg = entry.get("rotationGroup", {})
            source_slug = rg.get("slug")
            target_slug = self.rtg_slug_map.get(source_slug, source_slug)
            transformed["rotationGroup"] = {"slug": target_slug}
        elif execution_type == "user":
            user = entry.get("user", {})
            source_user = user.get("username")
            if source_user and self.remapping.is_skipped("users", source_user):
                return None
            transformed["user"] = {"username": self.remapping.map_value("users", source_user or "")}
        elif execution_type == "email":
            transformed["email"] = {"address": entry.get("email", {}).get("address", "")}
        elif execution_type == "policy_routing":
            target = entry.get("targetPolicy", {})
            source_policy = target.get("policySlug")
            transformed["targetPolicy"] = {
                "policySlug": self.policy_slug_map.get(source_policy, source_policy)
            }
        else:
            return None
        return transformed

    def _policy_sort_order(self, policy_slugs: List[str], details: Dict[str, Any]) -> List[str]:
        deps: Dict[str, Set[str]] = {slug: set() for slug in policy_slugs}
        for slug in policy_slugs:
            for step in details.get(slug, []) or []:
                for entry in step.get("entries", []):
                    if entry.get("executionType") == "policy_routing":
                        dep = entry.get("targetPolicy", {}).get("policySlug")
                        if dep and dep in deps and dep != slug:
                            deps[slug].add(dep)
        ordered: List[str] = []
        remaining = set(policy_slugs)
        while remaining:
            ready = sorted(s for s in remaining if not deps[s] - set(ordered))
            if not ready:
                ordered.extend(sorted(remaining))
                break
            ordered.extend(ready)
            remaining -= set(ready)
        return ordered

    def apply_escalation_policies(self) -> None:
        grouped = self._load_json("escalation_policies_inventory") or {}
        details = self._load_json("escalation_policy_details_inventory") or {}
        if not isinstance(grouped, dict) or not isinstance(details, dict):
            return

        all_slugs: List[str] = []
        policy_names: Dict[str, str] = {}
        for _team, policies in grouped.items():
            for entry in policies:
                policy = entry.get("policy", {})
                slug = policy.get("slug")
                if slug:
                    all_slugs.append(slug)
                    policy_names[slug] = policy.get("name", slug)

        for source_slug in self._policy_sort_order(all_slugs, details):
            if self.remapping.is_skipped("escalation_policies", source_slug):
                self._bump("escalation_policies", "skipped")
                continue
            source_team = self.policy_team_map.get(source_slug)
            if not source_team or self.remapping.is_skipped("teams", source_team):
                self._bump("escalation_policies", "skipped")
                continue
            target_team = self._target_team_slug(source_team)
            if not target_team:
                self._bump("escalation_policies", "failed")
                continue

            existing, status = self.client.get(f"policies/{source_slug}", allow_404=True)
            if status == 200 and existing:
                self.policy_slug_map[source_slug] = existing.get("slug", source_slug)
                self._bump("escalation_policies", "skipped")
                continue

            steps_out = []
            for step in details.get(source_slug, []) or []:
                entries_out = []
                for entry in step.get("entries", []):
                    transformed = self._transform_policy_entry(entry)
                    if transformed:
                        entries_out.append(transformed)
                if entries_out:
                    steps_out.append({"timeout": step.get("timeout", 0), "entries": entries_out})
            if not steps_out:
                self._bump("escalation_policies", "skipped")
                continue

            payload = {
                "name": policy_names.get(source_slug, source_slug),
                "teamSlug": target_team,
                "ignoreCustomPagingPolicies": False,
                "steps": steps_out,
            }
            result, code = self.client.post("policies", payload)
            if code == 200 and result:
                self.policy_slug_map[source_slug] = result.get("slug", source_slug)
                self._bump("escalation_policies", "created")
            else:
                self._bump("escalation_policies", "failed")

    def apply_routing_keys(self) -> None:
        routing_keys = self._load_json("routing_keys_inventory") or []
        for rk in routing_keys:
            if not isinstance(rk, dict):
                continue
            source_name = rk.get("routingKey")
            if not source_name or self.remapping.is_skipped("routing_keys", source_name):
                self._bump("routing_keys", "skipped")
                continue
            target_name = self.remapping.map_value("routing_keys", source_name)
            targets = []
            for target in rk.get("targets", []):
                source_policy = target.get("policySlug")
                if not source_policy:
                    url = target.get("policyUrl") or target.get("_policyUrl") or ""
                    source_policy = url.rstrip("/").split("/")[-1] if url else ""
                if source_policy and not self.remapping.is_skipped("escalation_policies", source_policy):
                    targets.append(self.policy_slug_map.get(source_policy, source_policy))
            if not targets:
                self._bump("routing_keys", "skipped")
                continue
            payload = {"routingKey": target_name, "targets": targets}
            result, code = self.client.post("org/routing-keys", payload)
            if code == 200 and result is not None:
                self._bump("routing_keys", "created")
            else:
                self._bump("routing_keys", "failed")

    def apply_alert_rules(self) -> None:
        rules = self._load_json("alert_rules_inventory") or []
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            rule_id = str(rule.get("id", ""))
            if not rule_id or self.remapping.is_skipped("alert_rules", rule_id):
                self._bump("alert_rules", "skipped")
                continue
            match_value = rule.get("alertValueMatch", "")
            if rule.get("alertField") == "routing_key" and match_value:
                match_value = self.remapping.map_value("routing_keys", match_value) or match_value
            payload = {
                "alertField": rule.get("alertField"),
                "alertValueMatch": match_value,
                "matchType": rule.get("matchType", "WILDCARD"),
                "rank": rule.get("rank", 1),
                "stopFlag": rule.get("stopFlag", False),
                "notes": rule.get("notes", ""),
            }
            if rule.get("annotations"):
                payload["annotations"] = rule["annotations"]
            result, code = self.client.post("alertRules", payload)
            if code == 200 and result is not None:
                self._bump("alert_rules", "created")
            else:
                self._bump("alert_rules", "failed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Splunk On-Call inventory to target org.")
    parser.add_argument("--apply", action="store_true", help="Execute writes (default is dry-run).")
    parser.add_argument("--inventory", default="inventory", help="Inventory directory path.")
    parser.add_argument("--remapping", default="inventory/remapping.json", help="Remapping file path.")
    args = parser.parse_args()

    env_path = load_dotenv()
    if env_path:
        log.info(f"Loaded environment from {env_path}")
    else:
        log.warning(f"No .env file found at {PROJECT_ROOT / '.env'}")

    required = {
        "TARGET_SPLUNK_ONCALL_API_ID": os.getenv("TARGET_SPLUNK_ONCALL_API_ID"),
        "TARGET_SPLUNK_ONCALL_API_KEY": os.getenv("TARGET_SPLUNK_ONCALL_API_KEY"),
        "TARGET_SPLUNK_ONCALL_ORG_SLUG": os.getenv("TARGET_SPLUNK_ONCALL_ORG_SLUG"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        log.critical("Missing target org credentials:")
        for name in missing:
            log.critical(f"  - {name}")
        log.critical(
            "Add TARGET_SPLUNK_ONCALL_API_ID, TARGET_SPLUNK_ONCALL_API_KEY, and "
            "TARGET_SPLUNK_ONCALL_ORG_SLUG to your .env (see .env.example)."
        )
        sys.exit(1)

    api_id = required["TARGET_SPLUNK_ONCALL_API_ID"]
    api_key = required["TARGET_SPLUNK_ONCALL_API_KEY"]
    org_slug = required["TARGET_SPLUNK_ONCALL_ORG_SLUG"]

    remapping_path = Path(args.remapping)
    if not remapping_path.exists():
        log.critical(f"Remapping file not found: {remapping_path}")
        sys.exit(1)

    remapping_data = json.loads(remapping_path.read_text())
    client = ApplyClient(api_id, api_key, org_slug, dry_run=not args.apply)
    pipeline = ApplyPipeline(
        client,
        Path(args.inventory),
        RemappingContext(remapping_data),
        Path(args.inventory) / "apply_report.json",
    )

    mode = "APPLY" if args.apply else "DRY-RUN"
    log.info(f"Starting apply pipeline ({mode}) for org '{org_slug}'")
    pipeline.run()


if __name__ == "__main__":
    main()
