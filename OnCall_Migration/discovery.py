#!/usr/bin/env python3
"""
Author: Brandon Blinderman
Date: 05/01/2026

Splunk On-Call Discovery Script.
Exports all discoverable configurations from the SOURCE organization to versioned JSON files.

Usage:
    export SOURCE_SPLUNK_ONCALL_API_ID="your-api-id"
    export SOURCE_SPLUNK_ONCALL_API_KEY="your-api-key"
    export SOURCE_SPLUNK_ONCALL_ORG_SLUG="your-org-slug"
    python3 discovery.py

Output: inventory/directory of JSON files ready for Terraform codification.
"""

import itertools
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

###
# Configuration
###
BASE_URL = "https://api.victorops.com/api-public/v1"
OUTPUT_DIR = Path("inventory")

REQUIRED_VARS = [
    "SOURCE_SPLUNK_ONCALL_API_ID",
    "SOURCE_SPLUNK_ONCALL_API_KEY",
    "SOURCE_SPLUNK_ONCALL_ORG_SLUG",
]

_missing = [var for var in REQUIRED_VARS if not os.getenv(var)]
if _missing:
    log.critical("Missing required environment variables: %s", ", ".join(_missing))
    sys.exit(1)

API_ID = os.getenv("SOURCE_SPLUNK_ONCALL_API_ID")
API_KEY = os.getenv("SOURCE_SPLUNK_ONCALL_API_KEY")
ORG_SLUG = os.getenv("SOURCE_SPLUNK_ONCALL_ORG_SLUG")

# Network session with native retry for 429 and 50x errors
SESSION = requests.Session()
retries = Retry(
    total=6,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)
SESSION.mount("https://", HTTPAdapter(max_retries=retries))
SESSION.headers.update(
    {
        "X-VO-Api-Id": API_ID,
        "X-VO-Api-Key": API_KEY,
        "Accept": "application/json",
    }
)


###
# Helper: Paginated API GET
###
def api_get(
    endpoint: str, params: dict[str, Any] | None = None
) -> list[Any] | dict[str, Any] | None:
    """
    Fetches all pages from a Splunk On-Call API endpoint.
    Handles cursor and offset pagination automatically.
    """
    url = endpoint if endpoint.startswith("http") else f"{BASE_URL}{endpoint}"
    merged: list[Any] = []
    is_list_response = False
    data: list[Any] | dict[str, Any] | None = None

    current_params = dict(params or {})
    current_params.setdefault("limit", 100)
    current_params.setdefault("offset", 0)
    page_num = 0

    while url:
        page_num += 1
        if page_num > 1:
            offset = current_params.get("offset", "cursor")
            log.info(
                "    [Paginating] Page %d (offset: %s) — %s", page_num, offset, endpoint
            )

        time.sleep(0.5)  # proactive throttle — Splunk On-Call API limit: 2 req/sec

        try:
            response = SESSION.get(url, params=current_params, timeout=30)
        except requests.RequestException as exc:
            log.error("    [Network Error] %s — %s", url, exc)
            raise RuntimeError(f"Failed to fetch {url}: {exc}")

        if response.status_code == 404:
            log.warning("    [Not Found] 404 for %s — skipping.", url)
            return None

        if response.status_code != 200:
            log.error(
                "    [HTTP %d] %s — %s", response.status_code, url, response.text[:200]
            )
            response.raise_for_status()

        data = response.json()

        if isinstance(data, list):
            is_list_response = True
            merged.extend(data)
            break

        if isinstance(data, dict):
            list_keys = [k for k, v in data.items() if isinstance(v, list)]

            if list_keys:
                is_list_response = True
                # Target the key containing a list of dicts to avoid pagination loops on metadata
                primary_key = next(
                    (k for k in list_keys if data[k] and isinstance(data[k][0], dict)),
                    list_keys[0],
                )
                page_items = data[primary_key]
                merged.extend(page_items)

                next_url = (
                    data.get("nextPage") or data.get("next_page") or data.get("next")
                )
                if next_url:
                    url = (
                        next_url
                        if next_url.startswith("http")
                        else f"{BASE_URL}{next_url}"
                    )
                    current_params = {}
                    continue

                limit = current_params.get("limit", 100)
                if (
                    page_items
                    and len(page_items) == limit
                    and isinstance(page_items[0], dict)
                ):
                    current_params["offset"] = current_params.get("offset", 0) + limit
                    continue

                break
            else:
                return data

        url = None

    return merged if is_list_response else data


###
# Helpers: Save, extract_list, fetch_per_entity
###
def save(name: str, data: Any) -> None:
    path = OUTPUT_DIR / f"{name}.json"
    path.write_text(json.dumps(data, indent=2))

    if isinstance(data, list):
        log.info("  -> Saved %d item(s) to %s", len(data), path)
    elif isinstance(data, dict):
        log.info("  -> Saved %d entity(ies) to %s", len(data), path)
    else:
        log.info("  -> Saved to %s", path)


def extract_list(data: Any, key: str) -> list[Any]:
    """Safely extracts a plain list from a raw api_get() response."""
    if data is None:
        return []
    if isinstance(data, list):
        if data and isinstance(data[0], list):
            return list(itertools.chain.from_iterable(data))
        return data
    if isinstance(data, dict):
        return data.get(key, []) or []
    return []


def fetch_per_entity(
    entities: list[dict[str, Any]],
    id_key: str,
    endpoint_factory: Callable[[str], str],
    filename: str,
    label: str = "entity",
) -> dict[str, Any]:
    """Helper for endpoints requiring a per-entity loop."""
    total = len(entities)
    results = {}
    skipped = 0

    for idx, entity in enumerate(entities, start=1):
        if not isinstance(entity, dict):
            raise TypeError(
                f"fetch_per_entity expects a list of dicts, got {type(entity).__name__}. "
                f"Ensure you are passing the extracted list, not raw api_get() responses."
            )

        entity_id = entity.get(id_key)
        if not entity_id:
            skipped += 1
            log.debug("  [Skip] %s at index %d has no %r key.", label, idx, id_key)
            continue

        log.info("  [%d/%d] %s: %s", idx, total, label, entity_id)
        data = api_get(endpoint_factory(entity_id))

        if data is not None:
            results[entity_id] = data
        else:
            log.info("    -> No data returned for %s %r — omitting.", label, entity_id)

    if skipped:
        log.warning(
            "  -> Skipped %d %s(s) with no %r identifier.", skipped, label, id_key
        )

    save(filename, results)
    return results


###
# Extractions
###
def _parse_timestamp(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def get_scheduled_overrides(teams: list[dict[str, Any]]) -> None:
    log.info("Fetching Scheduled Overrides...")
    now = datetime.now(timezone.utc)
    overrides: dict[str, Any] = {}
    total_fetched = total_active = total_dropped = 0

    for idx, team in enumerate(teams, start=1):
        team_slug = team.get("slug")
        if not team_slug:
            continue

        log.info("  [%d/%d] Team: %s", idx, len(teams), team_slug)
        raw = api_get(f"/team/{team_slug}/oncall/schedule/overrides")
        if not raw:
            log.info("    -> No overrides found.")
            continue

        raw_list = raw if isinstance(raw, list) else raw.get("overrides", [])
        total_fetched += len(raw_list)

        active = [
            o for o in raw_list if o.get("end") and _parse_timestamp(o["end"]) > now
        ]
        dropped = len(raw_list) - len(active)
        total_active += len(active)
        total_dropped += dropped

        log.info(
            "    -> %d override(s) found: %d active, %d expired (filtered).",
            len(raw_list),
            len(active),
            dropped,
        )

        if active:
            overrides[team_slug] = active

    log.info(
        "  Override summary: %d fetched across %d team(s), %d active kept, %d expired dropped.",
        total_fetched,
        len(teams),
        total_active,
        total_dropped,
    )
    save("scheduled_overrides_inventory", overrides or {})


###
# Main
###
if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    start_time = time.monotonic()

    log.info("=" * 60)
    log.info("Splunk On-Call Discovery — Org: %s", ORG_SLUG)
    log.info("Output directory: %s", OUTPUT_DIR.resolve())
    log.info("=" * 60)

    log.info("[Phase 1/3] Fetching global entities...")

    log.info("Fetching Users...")
    users = extract_list(api_get("/user"), "users")
    save("users_inventory", users)

    log.info("Fetching Teams...")
    teams = extract_list(api_get("/team"), "teams")
    save("teams_inventory", teams)

    log.info("Fetching Routing Keys...")
    routing_keys_raw = api_get("/org/routing-keys")
    save("routing_keys_inventory", extract_list(routing_keys_raw, "routingKeys"))

    log.info("Fetching Alert Rules...")
    rules_raw = api_get("/alert-rules") or api_get("/rules")
    rules_list = extract_list(rules_raw, "rules")
    rules_list.sort(key=lambda x: x.get("order", 0))
    save("alert_rules_inventory", rules_list)

    log.info("Fetching Integrations...")
    integrations_raw = api_get(f"/org/{ORG_SLUG}/integrations")
    save("integrations_inventory", extract_list(integrations_raw, "integrations"))

    log.info("Fetching Outbound Webhooks...")
    webhooks_raw = api_get(f"/org/{ORG_SLUG}/webhooks")
    save("outbound_webhooks_inventory", extract_list(webhooks_raw, "webhooks"))

    if users:
        log.info(
            "[Phase 2/3] Fetching user-scoped entities (%d user(s))...", len(users)
        )

        log.info("Fetching User Contact Methods...")
        fetch_per_entity(
            users,
            "username",
            lambda u: f"/user/{u}/contact-methods",
            "contact_methods_inventory",
            label="user",
        )

        log.info("Fetching User Paging Policies...")
        fetch_per_entity(
            users,
            "username",
            lambda u: f"/user/{u}/policies",
            "paging_policies_inventory",
            label="user",
        )
    else:
        log.warning("[Phase 2/3] No users found — skipping user-scoped entities.")

    if teams:
        log.info(
            "[Phase 3/3] Fetching team-scoped entities (%d team(s))...", len(teams)
        )

        log.info("Fetching Escalation Policies...")
        fetch_per_entity(
            teams,
            "slug",
            lambda t: f"/team/{t}/policies",
            "escalation_policies_inventory",
            label="team",
        )

        log.info("Fetching On-Call Schedules & Rotations...")
        fetch_per_entity(
            teams,
            "slug",
            lambda t: f"/team/{t}/oncall/schedule",
            "schedules_inventory",
            label="team",
        )

        get_scheduled_overrides(teams)
    else:
        log.warning("[Phase 3/3] No teams found — skipping team-scoped entities.")

    elapsed = time.monotonic() - start_time
    minutes, seconds = divmod(int(elapsed), 60)

    log.info("=" * 60)
    log.info(
        "Discovery complete in %dm %02ds. Review inventory/ before proceeding to Phase 2.",
        minutes,
        seconds,
    )
    log.info("=" * 60)
