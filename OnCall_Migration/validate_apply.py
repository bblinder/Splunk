import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


class PreFlightValidator:
    """Validates human edits in remapping.json and checks relational integrity against inventory."""

    def __init__(self, inventory_dir: Path, remapping_file: Path):
        self.inventory_dir = inventory_dir
        self.remapping_file = remapping_file
        self.errors = 0
        self.warnings = 0

    def _load_json(self, path: Path) -> Any:
        if not path.exists():
            return None
        with path.open("r") as f:
            return json.load(f)

    def _policy_slug_from_target(self, target: Dict[str, Any]) -> str:
        if target.get("policySlug"):
            return target["policySlug"]
        policy_url = target.get("policyUrl") or target.get("_policyUrl") or ""
        if policy_url:
            return policy_url.rstrip("/").split("/")[-1]
        return ""

    def _is_skipped(self, mappings: Dict[str, Any], key: str) -> bool:
        return key not in mappings or mappings.get(key) is None

    def validate(self) -> int:
        log.info("Starting Pre-Flight Validation...")
        remapping = self._load_json(self.remapping_file)
        if not remapping:
            log.error(f"Remapping file not found at {self.remapping_file}")
            self.errors += 1
            return self.errors

        self._validate_formats(remapping)
        self._validate_routing_key_policies(remapping)
        self._validate_policy_teams(remapping)
        self._validate_team_members(remapping)
        self._validate_team_admins(remapping)
        self._validate_alert_rules(remapping)

        log.info("-" * 40)
        log.info(f"Validation Complete: {self.errors} Errors, {self.warnings} Warnings/Skips.")
        if self.errors > 0:
            log.error("Validation FAILED. Please correct the errors in remapping.json before running apply.py.")
            return self.errors
        log.info("Validation PASSED. Ready for Apply phase.")
        return 0

    def _validate_formats(self, remapping: Dict[str, Any]) -> None:
        log.info("Validating target name/slug formats...")
        patterns = {
            "teams": re.compile(r"^[a-zA-Z0-9_-]+$"),
            "escalation_policies": re.compile(r"^[a-zA-Z0-9_-]+$"),
            "users": re.compile(r"^[a-zA-Z0-9_.@-]+$"),
            "routing_keys": re.compile(r"^.+$"),
            "alert_rules": re.compile(r"^.+$"),
            "outbound_webhooks": re.compile(r"^[a-zA-Z0-9_-]+$"),
        }

        for category, mappings in remapping.items():
            if not isinstance(mappings, dict):
                continue
            pattern = patterns.get(category, re.compile(r"^.+$"))
            for source, target in mappings.items():
                if target is None:
                    self.warnings += 1
                    log.warning(f"[{category}] '{source}' is marked for SKIP.")
                    continue
                if not isinstance(target, str) or not pattern.match(target):
                    self.errors += 1
                    if category in ("teams", "escalation_policies", "outbound_webhooks"):
                        log.error(
                            f"[{category}] Invalid target slug '{target}' for source '{source}'. "
                            "Only alphanumeric, dashes, and underscores allowed."
                        )
                    else:
                        log.error(f"[{category}] Invalid format '{target}' for source '{source}'.")

    def _validate_routing_key_policies(self, remapping: Dict[str, Any]) -> None:
        log.info("Validating routing key targets...")
        routing_keys = self._load_json(self.inventory_dir / "routing_keys_inventory.json") or []
        mapped_keys = remapping.get("routing_keys", {})
        mapped_policies = remapping.get("escalation_policies", {})

        for rk in routing_keys:
            if not isinstance(rk, dict):
                continue
            rk_name = rk.get("routingKey")
            if not rk_name or self._is_skipped(mapped_keys, rk_name):
                continue

            for target in rk.get("targets", []):
                if not isinstance(target, dict):
                    continue
                policy_slug = self._policy_slug_from_target(target)
                if not policy_slug:
                    continue
                if policy_slug not in mapped_policies:
                    self.errors += 1
                    log.error(
                        f"[routing_keys] '{rk_name}' targets policy '{policy_slug}' "
                        "which is missing from remapping.json."
                    )
                elif mapped_policies[policy_slug] is None:
                    self.errors += 1
                    log.error(
                        f"[routing_keys] '{rk_name}' targets policy '{policy_slug}' "
                        "which is marked to be SKIPPED."
                    )

    def _validate_policy_teams(self, remapping: Dict[str, Any]) -> None:
        log.info("Validating escalation policy team dependencies...")
        policies_grouped = self._load_json(self.inventory_dir / "escalation_policies_inventory.json") or {}
        mapped_teams = remapping.get("teams", {})
        mapped_policies = remapping.get("escalation_policies", {})

        if not isinstance(policies_grouped, dict):
            return

        for team_slug, policies in policies_grouped.items():
            for policy_entry in policies:
                if not isinstance(policy_entry, dict):
                    continue
                policy = policy_entry.get("policy", {})
                policy_slug = policy.get("slug")
                if not policy_slug or self._is_skipped(mapped_policies, policy_slug):
                    continue
                if self._is_skipped(mapped_teams, team_slug):
                    self.errors += 1
                    log.error(
                        f"[escalation_policies] Policy '{policy_slug}' belongs to skipped team '{team_slug}'."
                    )

    def _validate_team_members(self, remapping: Dict[str, Any]) -> None:
        log.info("Validating team member user references...")
        self._validate_team_user_refs(
            "team_members_inventory.json",
            remapping.get("teams", {}),
            remapping.get("users", {}),
            "team_members",
        )

    def _validate_team_admins(self, remapping: Dict[str, Any]) -> None:
        log.info("Validating team admin user references...")
        self._validate_team_user_refs(
            "team_admins_inventory.json",
            remapping.get("teams", {}),
            remapping.get("users", {}),
            "team_admins",
        )

    def _validate_team_user_refs(
        self,
        inventory_file: str,
        mapped_teams: Dict[str, Any],
        mapped_users: Dict[str, Any],
        label: str,
    ) -> None:
        team_data = self._load_json(self.inventory_dir / inventory_file) or {}
        if not isinstance(team_data, dict):
            return

        for team_slug, members in team_data.items():
            if self._is_skipped(mapped_teams, team_slug):
                continue
            if not isinstance(members, list):
                continue
            for member in members:
                if not isinstance(member, dict):
                    continue
                username = member.get("username")
                if not username:
                    continue
                if username not in mapped_users:
                    self.errors += 1
                    log.error(
                        f"[{label}] Team '{team_slug}' references user '{username}' "
                        "which is missing from remapping.json."
                    )
                elif mapped_users[username] is None:
                    self.errors += 1
                    log.error(
                        f"[{label}] Team '{team_slug}' references user '{username}' "
                        "which is marked to be SKIPPED."
                    )

    def _validate_alert_rules(self, remapping: Dict[str, Any]) -> None:
        alert_rules = remapping.get("alert_rules")
        if not alert_rules:
            return

        log.info("Validating alert rule routing key references...")
        rules = self._load_json(self.inventory_dir / "alert_rules_inventory.json") or []
        mapped_rules = remapping.get("alert_rules", {})
        mapped_keys = remapping.get("routing_keys", {})

        for rule in rules:
            if not isinstance(rule, dict):
                continue
            rule_id = str(rule.get("id", ""))
            if not rule_id or self._is_skipped(mapped_rules, rule_id):
                continue
            if rule.get("alertField") != "routing_key":
                continue
            match_value = rule.get("alertValueMatch", "")
            if not match_value:
                continue
            if match_value not in mapped_keys:
                self.errors += 1
                log.error(
                    f"[alert_rules] Rule {rule_id} matches routing key '{match_value}' "
                    "which is missing from remapping.json."
                )
            elif mapped_keys[match_value] is None:
                self.errors += 1
                log.error(
                    f"[alert_rules] Rule {rule_id} matches routing key '{match_value}' "
                    "which is marked to be SKIPPED."
                )


def main() -> None:
    validator = PreFlightValidator(Path("inventory"), Path("inventory/remapping.json"))
    exit_code = validator.validate()
    if exit_code:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
