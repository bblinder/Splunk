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
from exceptions import ApiError


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
            with self.assertRaises(ApiError):
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


if __name__ == "__main__":
    unittest.main()
