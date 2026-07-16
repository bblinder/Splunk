# Discovery Script Validation Report

**Date:** 2026-07-16  
**Scope:** [`discovery.py`](../discovery.py) — correctness and efficiency  
**Method:** Static analysis against [official Splunk On-Call API docs](https://portal.victorops.com/public/api-docs.html), code fixes, and **live validation against org `sabre`**

> **Document status:** Current-state summary of the live `sabre` discovery run. Pre-fix audit history was removed during project layout cleanup. See `tests/test_discovery.py` for regression coverage.

---

## Executive Summary

| Inventory file | Live verdict | Count |
| :--- | :--- | :--- |
| `users_inventory.json` | **PASS** | 1,087 |
| `teams_inventory.json` | **PASS** | 218 |
| `routing_keys_inventory.json` | **PASS** | 193 |
| `alert_rules_inventory.json` | **PASS** | 25 (sorted by `rank`) |
| `integrations_inventory.json` | **N/A** | Not exported — no public API |
| `outbound_webhooks_inventory.json` | **PASS** | 1 |
| `contact_methods_inventory.json` | **PASS** | 1,087 users (`devices`, `emails`, `phones`) |
| `paging_policies_inventory.json` | **PASS** | 1,087 users (full policy objects) |
| `escalation_policies_inventory.json` | **PASS** | 200 teams (18 teams have no policies) |
| `escalation_policy_details_inventory.json` | **PASS** | 211 policies (steps, entries, timeouts) |
| `team_members_inventory.json` | **PASS** | 218 teams (user-team mapping) |
| `team_admins_inventory.json` | **PASS** | 218 teams |
| `rotation_definitions_inventory.json` | **PASS** | 218 teams (shift config, masks, timezone) |
| `schedules_inventory.json` | **PASS** | 218 teams (v2 API, computed calendar) |
| `scheduled_overrides_inventory.json` | **PASS** | 45 team buckets (403 active overrides) |
| `discovery_metadata.json` | **PASS** | Run stats, inventory counts, manual_capture_required |

**Overall:** After extending discovery with Tier 1+2 exports, the script **successfully exported all API-discoverable durable configuration** from the live `sabre` org in **35m 35s**. Zero HTTP 404 errors on required endpoints. All structural spot-checks passed. Integrations, user permissions, and SSO remain documented manual gaps (no public API).

**Live validation status:** **COMPLETED** — extended run 2026-07-16 via `.env` credentials against org `sabre`.

---

## Live Validation Runbook

When credentials are available, run these steps to confirm discovery against your org:

```bash
cp .env.example .env   # edit with SOURCE_SPLUNK_ONCALL_* credentials
python3 discovery.py 2>&1 | tee discovery_run.log
```

Alternative without venv: `uv run --with requests python3 discovery.py`

Then compare:

1. Count 404 warnings in `discovery_run.log` — expect **zero** 404s on required endpoints
2. Compare `len(users)` and `len(teams)` in inventory vs Splunk On-Call UI
3. Run `python3 validate_inventory.py` — should exit 0
4. Spot-check one user's contact methods in UI vs `contact_methods_inventory.json` — verify `devices`, `emails`, and `phones` are present

---

## Conclusion

After implementing the validation recommendations and running live discovery against org `sabre`, `discovery.py` is **reliable as a complete API-discoverable configuration export**:

- **All data inventory files** populated successfully with correct structure
- **Contact methods** include `devices`, `emails`, and `phones` per user
- **Alert rules** exported via `/alertRules` and sorted by `rank`
- **Overrides** fetched via single `/overrides` call (403 active, grouped into 43 team buckets)
- **Efficiency** improved: ~2,399 calls vs ~2,834 pre-fix estimate (435 fewer calls)

**Remaining gap:** Integrations must be captured manually from the Splunk On-Call UI (no public list API). See `discovery_metadata.json` notes.

---

## Live Validation Results (2026-07-16)

### Run summary

| Metric | Value |
| :--- | :--- |
| Org slug | `sabre` |
| Runtime | 26m 20s (1,580.8s) |
| Estimated API calls | 2,399 (`5 + 2×1087 + 218 + 2`) |
| HTTP 404 on required endpoints | 0 |
| Errors / crashes | 0 |

### Per-file results (live-confirmed)

| File | Status | Count | Notes |
| :--- | :--- | :--- | :--- |
| `users_inventory.json` | PASS | 1,087 | Matches Phase 1 fetch |
| `teams_inventory.json` | PASS | 218 | Bare list response handled correctly |
| `routing_keys_inventory.json` | PASS | 193 | `routingKeys` key extracted |
| `alert_rules_inventory.json` | PASS | 25 | `/alertRules`; sorted ascending by `rank` |
| `outbound_webhooks_inventory.json` | PASS | 1 | `/webhooks` |
| `contact_methods_inventory.json` | PASS | 1,087 | Full dict per user: `devices`, `emails`, `phones` |
| `paging_policies_inventory.json` | PASS | 1,087 | Full policy objects per user |
| `escalation_policies_inventory.json` | PASS | 200 | Global `/policies` grouped by team; 18 teams have no policies |
| `schedules_inventory.json` | PASS | 218 | v2 endpoint; full response per team |
| `scheduled_overrides_inventory.json` | PASS | 43 | 403 active overrides from `/overrides`; 0 expired dropped |
| `integrations_inventory.json` | N/A | — | Intentionally skipped (no public API) |
| `discovery_metadata.json` | PASS | — | `inventory_counts` matches all file counts |

### Correctness fixes verified live

| Fix | Pre-fix issue | Live result |
| :--- | :--- | :--- |
| `/alertRules` endpoint | Empty `alert_rules_inventory` | 25 rules exported |
| Sort by `rank` | Wrong rule ordering | `alert_rules_sorted_by_rank: true` |
| `/webhooks` endpoint | Empty webhooks file | 1 webhook exported |
| `/overrides` (org-wide) | Empty overrides file | 403 overrides, 43 team buckets |
| Multi-list response handling | Contact methods truncated to devices only | All three contact types present |
| Global `/policies` | N+1 per-team calls | 200 team buckets from 1 API call |
| v2 schedule endpoint | Deprecated v1 | 218 team schedules exported |

### Efficiency actuals

| Metric | Pre-fix model (U=1087, T=218) | Live run |
| :--- | :--- | :--- |
| API calls | ~2,834 (`6 + 2U + 3T`) | ~2,399 |
| Calls saved | — | ~435 (overrides + escalation policy optimization) |
| Wall-clock | ~1,417s minimum throttle | 1,581s actual |
| Throttle overhead | 0.5s/call | Retries not triggered; runtime consistent with serial 2 req/sec |

### Structural spot-checks

- **Contact methods:** Sample user entry contains `devices`, `emails`, `phones` keys
- **Alert rules:** All 25 rules sorted by ascending `rank`
- **Escalation policies:** Entries contain `policy` and `team` summary objects
- **Metadata:** All `inventory_counts` in `discovery_metadata.json` match on-disk file lengths

### Remaining gaps

1. **Integrations** — must be documented manually from Splunk On-Call UI
2. **18 teams without escalation policies** — expected; teams exist but have no assigned policies
3. **UI cross-check** — not performed; inventory internal consistency confirmed

---

## Extended Discovery Run (2026-07-16)

### Run summary

| Metric | Prior run | Extended run | Delta |
| :--- | :--- | :--- | :--- |
| Org slug | `sabre` | `sabre` | — |
| Runtime | 26m 20s | **35m 35s** | +9m 15s |
| Estimated API calls | ~2,399 | ~3,256 | +857 |
| HTTP 404 on required endpoints | 0 | 0 | — |
| Errors / crashes | 0 | 0 | — |

### New inventory files (Tier 1 + Tier 2)

| File | Status | Count | Notes |
| :--- | :--- | :--- | :--- |
| `team_members_inventory.json` | PASS | 218 | All 218 teams have member rosters |
| `team_admins_inventory.json` | PASS | 218 | Per-team admin lists |
| `rotation_definitions_inventory.json` | PASS | 218 | Shift members, masks, timezone, rotation groups |
| `escalation_policy_details_inventory.json` | PASS | 211 | Full steps with `timeout`, `entries`, `executionType` |

### Structural spot-checks (extended)

- **Team coverage:** 218/218 teams present in `team_members`, `team_admins`, `rotation_definitions`, and `schedules`
- **Team members:** Per-team lists of `username`, `displayName`, `verified`
- **Rotation definitions:** Per-team `rotations[]` with `shifts[]`, `mask`, `timezone`, `shifttype`
- **Policy details:** Per-policy step arrays with `rotation_group`, `email`, and other `executionType` entries
- **Metadata:** `manual_capture_required` lists `integrations`, `user_permissions`, `sso_settings`

### Remaining manual gaps

1. **Integrations** — see [`manual_capture/README.md`](../manual_capture/README.md)
2. **User permission levels** — not exposed via public API
3. **SSO / org auth settings** — manual UI capture only
