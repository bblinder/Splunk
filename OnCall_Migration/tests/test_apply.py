"""Unit tests for apply.py."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apply import ApplyClient, ApplyPipeline, RemappingContext


class FakeResponse:
    def __init__(self, payload: object, status_code: int = 200):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> object:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class ApplyPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.inventory_dir = Path(self.temp_dir.name)
        self.remapping = RemappingContext(
            {
                "users": {"alice": "alice"},
                "teams": {"team-alpha": "team-alpha"},
                "routing_keys": {"ALPHA": "ALPHA"},
                "escalation_policies": {"pol-alpha": "pol-alpha"},
                "alert_rules": {"1": "1"},
                "outbound_webhooks": {},
            }
        )
        self._write_inventory()
        self.client = ApplyClient("id", "key", "target-org", dry_run=True)
        self.pipeline = ApplyPipeline(
            self.client,
            self.inventory_dir,
            self.remapping,
            self.inventory_dir / "apply_report.json",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_inventory(self) -> None:
        fixtures = {
            "users_inventory.json": [
                {
                    "username": "alice",
                    "firstName": "Alice",
                    "lastName": "Example",
                    "email": "alice@example.com",
                }
            ],
            "teams_inventory.json": [{"slug": "team-alpha", "name": "Alpha Team"}],
            "team_members_inventory.json": {"team-alpha": [{"username": "alice"}]},
            "team_admins_inventory.json": {"team-alpha": [{"username": "alice"}]},
            "rotation_definitions_inventory.json": {
                "team-alpha": {
                    "rotations": [
                        {
                            "label": "Primary",
                            "shifts": [
                                {
                                    "label": "Day",
                                    "timezone": "UTC",
                                    "start": "2020-01-01T00:00:00Z",
                                    "duration": 7,
                                    "shifttype": "std",
                                    "mask": {"day": {}, "time": []},
                                    "shiftMembers": [{"username": "alice"}],
                                }
                            ],
                        }
                    ]
                }
            },
            "escalation_policies_inventory.json": {
                "team-alpha": [{"policy": {"slug": "pol-alpha", "name": "Alpha Policy"}}]
            },
            "escalation_policy_details_inventory.json": {
                "pol-alpha": [
                    {
                        "timeout": 0,
                        "entries": [
                            {
                                "executionType": "rotation_group",
                                "rotationGroup": {"slug": "rtg-src", "label": "Primary"},
                            }
                        ],
                    }
                ]
            },
            "routing_keys_inventory.json": [
                {"routingKey": "ALPHA", "targets": [{"policySlug": "pol-alpha"}]}
            ],
            "alert_rules_inventory.json": [
                {
                    "id": 1,
                    "alertField": "routing_key",
                    "alertValueMatch": "ALPHA",
                    "matchType": "WILDCARD",
                    "rank": 1,
                    "stopFlag": False,
                }
            ],
        }
        for name, data in fixtures.items():
            (self.inventory_dir / name).write_text(json.dumps(data))

    def test_dry_run_writes_report_without_http_posts(self) -> None:
        self.client.session.get = mock.MagicMock(return_value=FakeResponse({}, status_code=404))
        self.client.session.post = mock.MagicMock()

        report = self.pipeline.run()

        self.assertTrue(self.pipeline.report_path.exists())
        self.assertTrue(report["dry_run"])
        self.client.session.post.assert_not_called()

    def test_apply_posts_with_remapped_payload(self) -> None:
        self.client.dry_run = False

        def fake_get(url, timeout=30):
            if url.endswith("/user/alice"):
                return FakeResponse({}, status_code=404)
            if url.endswith("/team"):
                return FakeResponse([], status_code=200)
            if "/members" in url:
                return FakeResponse({"members": []}, status_code=200)
            if "/rotations" in url:
                return FakeResponse(
                    {"rotationGroups": [{"label": "Primary", "slug": "rtg-target"}]},
                    status_code=200,
                )
            if "/policies/pol-alpha" in url:
                return FakeResponse({}, status_code=404)
            return FakeResponse({}, status_code=404)

        self.client.session.get = mock.MagicMock(side_effect=fake_get)
        posted = []

        def fake_post(url, json=None, timeout=30):
            posted.append((url, json))
            if url.endswith("/user"):
                return FakeResponse({"username": "alice"}, status_code=200)
            if url.endswith("/team"):
                return FakeResponse({"slug": "team-target", "name": "Alpha Team"}, status_code=200)
            if url.endswith("/members"):
                return FakeResponse({"members": [{"username": "alice"}]}, status_code=200)
            if "/rotations" in url:
                return FakeResponse(
                    {"rotationGroups": [{"label": "Primary", "slug": "rtg-target"}]},
                    status_code=200,
                )
            if url.endswith("/policies"):
                return FakeResponse({"slug": "pol-target"}, status_code=200)
            if url.endswith("/org/routing-keys"):
                return FakeResponse({"routingKey": "ALPHA"}, status_code=200)
            if url.endswith("/alertRules"):
                return FakeResponse({"id": 99}, status_code=200)
            return FakeResponse({}, status_code=200)

        self.client.session.post = mock.MagicMock(side_effect=fake_post)

        with mock.patch.object(self.client.rate_limiter, "wait"):
            self.pipeline.run()

        user_post = next(body for url, body in posted if url.endswith("/user"))
        self.assertEqual(user_post["username"], "alice")
        policy_post = next(body for url, body in posted if url.endswith("/policies"))
        self.assertEqual(policy_post["teamSlug"], "team-target")
        self.assertEqual(
            policy_post["steps"][0]["entries"][0]["rotationGroup"]["slug"],
            "rtg-target",
        )


class ApplyMainEnvTest(unittest.TestCase):
    def test_main_exits_when_target_env_missing(self) -> None:
        import apply as apply_module

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("apply.load_dotenv", return_value=None):
                with mock.patch("sys.argv", ["apply.py"]):
                    with self.assertRaises(SystemExit):
                        apply_module.main()

    def test_main_runs_when_target_env_present(self) -> None:
        import apply as apply_module

        env = {
            "TARGET_SPLUNK_ONCALL_API_ID": "id",
            "TARGET_SPLUNK_ONCALL_API_KEY": "key",
            "TARGET_SPLUNK_ONCALL_ORG_SLUG": "org",
        }
        with tempfile.TemporaryDirectory() as tmp:
            inventory = Path(tmp) / "inventory"
            inventory.mkdir()
            (inventory / "users_inventory.json").write_text("[]")
            (inventory / "teams_inventory.json").write_text("[]")
            remapping = Path(tmp) / "remapping.json"
            remapping.write_text(
                json.dumps(
                    {
                        "users": {},
                        "teams": {},
                        "routing_keys": {},
                        "escalation_policies": {},
                        "alert_rules": {},
                        "outbound_webhooks": {},
                    }
                )
            )
            with mock.patch.dict(os.environ, env, clear=True):
                with mock.patch("apply.load_dotenv", return_value=Path(tmp) / ".env"):
                    with mock.patch.object(apply_module.ApplyPipeline, "run", return_value={}) as mock_run:
                        with mock.patch(
                            "sys.argv",
                            [
                                "apply.py",
                                "--inventory",
                                str(inventory),
                                "--remapping",
                                str(remapping),
                            ],
                        ):
                            apply_module.main()
            mock_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
