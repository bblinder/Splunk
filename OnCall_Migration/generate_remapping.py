import json
import logging
from pathlib import Path
from typing import Any, Dict

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


class RemappingGenerator:
    """Generates a remapping.json template from the discovery inventory."""

    def __init__(self, inventory_dir: Path, output_file: Path):
        self.inventory_dir = inventory_dir
        self.output_file = output_file

    def _load_json(self, filename: str) -> Any:
        path = self.inventory_dir / filename
        if not path.exists():
            log.warning(f"File not found: {path}")
            return []
        try:
            with path.open("r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            log.error(f"Failed to parse {path}")
            return []

    def generate(self) -> Dict[str, Dict[str, str]]:
        remapping = {
            "users": {},
            "teams": {},
            "routing_keys": {},
            "escalation_policies": {},
            "alert_rules": {},
            "outbound_webhooks": {},
        }

        users = self._load_json("users_inventory.json")
        for u in users:
            if isinstance(u, dict) and "username" in u:
                remapping["users"][u["username"]] = u["username"]

        teams = self._load_json("teams_inventory.json")
        for t in teams:
            if isinstance(t, dict) and "slug" in t:
                remapping["teams"][t["slug"]] = t["slug"]

        routing_keys = self._load_json("routing_keys_inventory.json")
        for rk in routing_keys:
            if isinstance(rk, dict) and "routingKey" in rk:
                remapping["routing_keys"][rk["routingKey"]] = rk["routingKey"]

        policies_grouped = self._load_json("escalation_policies_inventory.json")
        if isinstance(policies_grouped, dict):
            for _team_slug, policies in policies_grouped.items():
                for p in policies:
                    policy = p.get("policy", {})
                    slug = policy.get("slug")
                    if slug:
                        remapping["escalation_policies"][slug] = slug

        alert_rules = self._load_json("alert_rules_inventory.json")
        for rule in alert_rules:
            if isinstance(rule, dict) and rule.get("id") is not None:
                remapping["alert_rules"][str(rule["id"])] = str(rule["id"])

        webhooks = self._load_json("outbound_webhooks_inventory.json")
        for wh in webhooks:
            if isinstance(wh, dict) and wh.get("slug"):
                remapping["outbound_webhooks"][wh["slug"]] = wh["slug"]

        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        with self.output_file.open("w") as f:
            json.dump(remapping, f, indent=2)

        log.info(f"Generated remapping template at {self.output_file}")
        log.info(
            "Counts: %d users, %d teams, %d routing keys, %d policies, %d alert rules, %d webhooks.",
            len(remapping["users"]),
            len(remapping["teams"]),
            len(remapping["routing_keys"]),
            len(remapping["escalation_policies"]),
            len(remapping["alert_rules"]),
            len(remapping["outbound_webhooks"]),
        )

        return remapping


if __name__ == "__main__":
    generator = RemappingGenerator(Path("inventory"), Path("inventory/remapping.json"))
    generator.generate()
