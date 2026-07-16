"""Unit tests for discovery.py (mocked HTTP — no live API calls)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

os.environ.setdefault("SOURCE_SPLUNK_ONCALL_API_ID", "test-id")
os.environ.setdefault("SOURCE_SPLUNK_ONCALL_API_KEY", "test-key")
os.environ.setdefault("SOURCE_SPLUNK_ONCALL_ORG_SLUG", "test-org")

from discovery import DiscoveryPipeline, VictorOpsClient


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


class VictorOpsClientTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = VictorOpsClient("test-id", "test-key", "test-org")

    def test_get_returns_full_dict_for_multi_list_responses(self) -> None:
        payload = {
            "devices": [{"deviceType": "push"}],
            "emails": [{"deviceType": "email"}],
            "phones": [{"deviceType": "phone"}],
        }
        self.client.session.get = mock.MagicMock(return_value=FakeResponse(payload))

        with mock.patch.object(self.client.rate_limiter, "wait"):
            result = self.client.get("user/alice/contact-methods")

        self.assertIsInstance(result, dict)
        self.assertEqual(set(result.keys()), {"devices", "emails", "phones"})

    def test_get_required_404_raises(self) -> None:
        self.client.session.get = mock.MagicMock(return_value=FakeResponse({}, status_code=404))

        with mock.patch.object(self.client.rate_limiter, "wait"):
            with self.assertRaises(RuntimeError):
                self.client.get("alertRules", required=True)

    def test_get_paginate_false_returns_rotation_dict(self) -> None:
        payload = {"rotations": [{"name": "primary"}]}
        self.client.session.get = mock.MagicMock(return_value=FakeResponse(payload))

        with mock.patch.object(self.client.rate_limiter, "wait"):
            result = self.client.get("team/team-a/rotations", use_v2=True, paginate=False)

        self.assertEqual(result, payload)


class DiscoveryPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = VictorOpsClient("test-id", "test-key", "test-org")
        self.pipeline = DiscoveryPipeline(self.client, Path("inventory"))

    def test_extract_list_from_bare_list(self) -> None:
        data = [{"username": "alice"}]
        self.assertEqual(self.pipeline.extract_list(data, "users"), data)

    def test_extract_list_flattens_nested_lists(self) -> None:
        data = [[{"username": "alice"}], [{"username": "bob"}]]
        result = self.pipeline.extract_list(data)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["username"], "alice")
        self.assertEqual(result[1]["username"], "bob")

    def test_is_override_active_without_end(self) -> None:
        now = datetime.now(timezone.utc)
        self.assertTrue(self.pipeline.is_override_active({"publicId": "o1"}, now))

    def test_is_override_active_expired(self) -> None:
        now = datetime.now(timezone.utc)
        override = {"publicId": "o2", "end": "2000-01-01T00:00:00Z"}
        self.assertFalse(self.pipeline.is_override_active(override, now))

    def test_is_override_active_invalid_end(self) -> None:
        now = datetime.now(timezone.utc)
        override = {"publicId": "o3", "end": "not-a-timestamp"}
        self.assertFalse(self.pipeline.is_override_active(override, now))

    def test_get_scheduled_overrides_groups_by_team(self) -> None:
        payload = {
            "overrides": [
                {
                    "publicId": "active-1",
                    "end": "2099-01-01T00:00:00Z",
                    "assignments": [{"team": "team-a"}, {"team": "team-b"}],
                },
                {
                    "publicId": "expired-1",
                    "end": "2000-01-01T00:00:00Z",
                    "assignments": [{"team": "team-a"}],
                },
                {
                    "publicId": "unassigned-1",
                    "end": "2099-01-01T00:00:00Z",
                    "assignments": [],
                },
            ]
        }
        self.client.get = mock.MagicMock(return_value=payload)

        grouped = self.pipeline.get_scheduled_overrides()

        self.assertIn("team-a", grouped)
        self.assertIn("team-b", grouped)
        self.assertIn("_unassigned", grouped)
        self.assertEqual(len(grouped["team-a"]), 1)
        self.assertEqual(grouped["team-a"][0]["publicId"], "active-1")

    def test_fetch_per_entity_concurrent(self) -> None:
        users = [{"username": "alice"}, {"username": "bob"}]
        self.client.get = mock.MagicMock(
            side_effect=[
                {"devices": [], "emails": [], "phones": []},
                {"devices": [], "emails": [], "phones": []},
            ]
        )

        results = self.pipeline.fetch_per_entity_concurrent(
            users, "username", lambda u: f"user/{u}/contact-methods", "user"
        )

        self.assertEqual(len(results), 2)
        self.assertIn("alice", results)
        self.assertIn("bob", results)

    def test_fetch_per_entity_concurrent_passes_paginate_false(self) -> None:
        teams = [{"slug": "team-a"}]
        self.client.get = mock.MagicMock(return_value={"rotations": [{"name": "primary"}]})

        results = self.pipeline.fetch_per_entity_concurrent(
            teams,
            "slug",
            lambda t: f"team/{t}/rotations",
            "team",
            use_v2=True,
            paginate=False,
        )

        self.client.get.assert_called_once_with(
            "team/team-a/rotations", use_v2=True, paginate=False
        )
        self.assertEqual(results["team-a"], {"rotations": [{"name": "primary"}]})


class DiscoveryPipelineSummaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = VictorOpsClient("test-id", "test-key", "test-org")
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name)
        self.pipeline = DiscoveryPipeline(self.client, self.output_dir)
        self.pipeline.inventory_counts = {
            "users_inventory": 1,
            "teams_inventory": 1,
            "routing_keys_inventory": 1,
            "alert_rules_inventory": 1,
            "outbound_webhooks_inventory": 1,
            "scheduled_overrides_inventory": 1,
        }
        self._write_fixtures()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_fixtures(self) -> None:
        fixtures = {
            "teams_inventory": [
                {"name": "Alpha Team", "slug": "team-alpha", "memberCount": 2},
            ],
            "users_inventory": [
                {
                    "username": "alice",
                    "displayName": "Alice Example",
                    "email": "alice@example.com",
                },
            ],
            "routing_keys_inventory": [
                {
                    "routingKey": "ALPHA-KEY",
                    "targets": [
                        {
                            "policyName": "Alpha Policy",
                            "_teamUrl": "/api-public/v1/team/team-alpha",
                        }
                    ],
                },
            ],
            "alert_rules_inventory": [
                {
                    "rank": 1,
                    "alertField": "routing_key",
                    "alertValueMatch": "ALPHA-KEY",
                    "matchType": "WILDCARD",
                    "stopFlag": False,
                    "annotations": [
                        {
                            "fieldValue": "https://example.com/webhook?sig=secret-token",
                        }
                    ],
                },
            ],
            "outbound_webhooks_inventory": [
                {
                    "label": "Test Webhook",
                    "slug": "wh-test",
                    "url": "https://example.com/webhook?sig=secret-token",
                },
            ],
            "team_members_inventory": {
                "team-alpha": [
                    {"username": "alice"},
                    {"username": "bob"},
                ],
            },
            "team_admins_inventory": {
                "team-alpha": [{"username": "alice"}],
            },
            "rotation_definitions_inventory": {
                "team-alpha": {
                    "rotations": [
                        {"label": "Primary"},
                        {"label": "Secondary"},
                    ],
                },
            },
            "escalation_policies_inventory": {
                "team-alpha": [
                    {"policy": {"slug": "pol-1", "name": "Alpha Policy"}},
                    {"policy": {"slug": "pol-2", "name": "Backup Policy"}},
                ],
            },
            "scheduled_overrides_inventory": {
                "team-alpha": [{"publicId": "override-1"}],
            },
        }
        for name, data in fixtures.items():
            path = self.output_dir / f"{name}.json"
            path.write_text(json.dumps(data))

    def test_save_inventory_summary_writes_markdown(self) -> None:
        self.pipeline.save_inventory_summary(65.0)

        summary_path = self.output_dir / "inventory_summary.md"
        self.assertTrue(summary_path.exists())
        content = summary_path.read_text()

        self.assertIn("test-org", content)
        self.assertIn("Alpha Team", content)
        self.assertIn("ALPHA-KEY", content)
        self.assertIn("| 1 |", content)
        self.assertIn("alice", content)
        self.assertIn("Alice Example", content)
        self.assertIn("Primary, Secondary", content)

    def test_save_inventory_summary_redacts_sensitive_fields(self) -> None:
        self.pipeline.save_inventory_summary(65.0)
        content = (self.output_dir / "inventory_summary.md").read_text()

        self.assertNotIn("https://example.com/webhook", content)
        self.assertNotIn("secret-token", content)
        self.assertNotIn("alice@example.com", content)
        self.assertIn("Test Webhook", content)
        self.assertIn("wh-test", content)


if __name__ == "__main__":
    unittest.main()
