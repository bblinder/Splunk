# Splunk On-Call Migration Guide

General reference for exporting Splunk On-Call (VictorOps) configuration from a source org. Use this document as a project spec for continuing migration work.

---

## Objective

Build a **complete, durable configuration snapshot** of a Splunk On-Call org:

1. **API discovery** — export all public-API-discoverable config to JSON
2. **Manual capture** — document gaps the API cannot list (integrations, global permissions, SSO)
3. **Apply** — provision target org from inventory + remapping

Terraform was evaluated and rejected for the apply step: the `splunk/victorops` provider doesn't cover all resources and is inconsistently maintained. Target-org provisioning is implemented in `apply.py` instead.

---
 
## Repository layout

| Path | Purpose | 
| :--- | :--- |
| `discovery.py` | Read-only exporter. Four-phase pipeline, serial API throttle |
| `validate_inventory.py` | Post-discovery consistency checks (no API) |
| `generate_remapping.py` | Build `remapping.json` template from inventory |
| `validate_apply.py` | Pre-flight remapping + relational integrity checks |
| `apply.py` | Target-org provisioning (dry-run default; `--apply` to write) |
| `env_loader.py` | Project-root `.env` loading (shared by `discovery.py` and `apply.py`) |
| `tests/` | Mocked unit tests (no live API calls) |
| `docs/` | Migration guide and post-discovery validation template (`VALIDATION_REPORT.md`) |
| `inventory/` | API export output and `remapping.json` (gitignored) |
| `manual_capture/` | Manual capture templates and operator notes (gitignored) |
| `README.md` | Usage, pipeline, quick reference |
| `.env` | Source/target API credentials (gitignored) |
| `.env.example` | Credential template |

**Setup:**
```bash
# Option A: venv + pip
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Option B: uv
uv venv && uv pip install -r requirements.txt

cp .env.example .env   # then edit with your credentials
```

Scripts load `.env` from the project root automatically (not cwd-dependent). Shell `export` values take precedence over `.env`.

**Source (discovery)** — set in `.env` or environment:
```
SOURCE_SPLUNK_ONCALL_API_ID
SOURCE_SPLUNK_ONCALL_API_KEY
SOURCE_SPLUNK_ONCALL_ORG_SLUG
```

**Run scripts:**
```bash
python3 discovery.py
# uv (project venv):  uv run python3 discovery.py
# uv (ephemeral):     uv run --with requests python3 discovery.py
```

Replace `discovery.py` with any pipeline script (`validate_inventory.py`, `generate_remapping.py`, `validate_apply.py`, `apply.py`).

**Run tests:** 
```bash
python3 -m unittest discover -s tests -t . -v
# uv: uv run python3 -m unittest discover -s tests -t . -v
```

---

## Phase 1: API discovery

### Pipeline

| Phase | Scope | Exports |
| :--- | :--- | :--- |
| 1/4 Global | Org-wide list endpoints | users, teams, routing keys, alert rules, webhooks |
| 2/4 User-scoped | Per-user loop | contact methods, paging policies |
| 3/4 Team-scoped | Per-team loop | members, admins, rotation definitions, escalation summaries, schedules, active overrides |
| 4/4 Policy details | Per unique policy slug | full escalation steps and entries |

Integrations are skipped — no public list endpoint exists.

### Inventory files

| File | Scope | Notes |
| :--- | :--- | :--- |
| `users_inventory.json` | Global | User accounts |
| `teams_inventory.json` | Global | Team slugs and metadata |
| `routing_keys_inventory.json` | Global | Alert routing keys |
| `alert_rules_inventory.json` | Global | Rules sorted by `rank` |
| `outbound_webhooks_inventory.json` | Global | Outbound webhook definitions |
| `contact_methods_inventory.json` | Per-user | Devices, emails, phones |
| `paging_policies_inventory.json` | Per-user | User paging rules |
| `team_members_inventory.json` | Per-team | User-to-team mapping |
| `team_admins_inventory.json` | Per-team | Team administrators |
| `escalation_policies_inventory.json` | Per-team | Policy summaries (name, slug) |
| `escalation_policy_details_inventory.json` | Per-policy | Steps, entries, timeouts |
| `rotation_definitions_inventory.json` | Per-team | Shift config: members, masks, timezone |
| `schedules_inventory.json` | Per-team | Computed on-call calendar (not rotation config) |
| `scheduled_overrides_inventory.json` | Per-team | Active overrides only |
| `discovery_metadata.json` | Global | Counts, timestamps, `files_written`, `manual_capture_required` |
| `inventory_summary.md` | Global | Human-readable Markdown catalog |
| `remapping.json` | Global | Source-to-target identifier map (steps 3–5) |
| `apply_report.json` | Global | Per-step apply stats and slug maps (after apply) |

### Runtime

Discovery is read-only and throttled (~2 req/sec). Large orgs (1,000+ users, 200+ teams) expect ~30–40 minutes and ~3,000+ API calls. Output goes to `inventory/`; logs to `discovery_run.log`.

### Deliberately excluded

Incidents, alerts, point-in-time on-call snapshots, expired overrides, reporting APIs, per-user team lists (use team-centric members instead).

### Key implementation notes

- `VictorOpsClient.get()` returns full dicts for multi-list responses (e.g. contact methods)
- `required=True` on critical endpoints raises on 404
- Overrides fetched org-wide via `GET /overrides`, filtered to active only
- Escalation policies: global `GET /policies` grouped by team; details via `GET /policies/{slug}`
- Rotations: `GET /v2/team/{slug}/rotations` (distinct from schedule calendar)

---

## Phase 2: Manual capture

Three gaps have no public API. Capture from the Splunk On-Call portal and your identity provider.

| Gap | Location | Source |
| :--- | :--- | :--- |
| Integrations | `manual_capture/integrations/` | Portal → Integrations |
| User permissions | `manual_capture/user_permissions/` | Settings → Organization → Users |
| SSO settings | `manual_capture/sso/` | IdP admin console |

**Workflow:** `manual_capture/README.md`  
**Status tracker:** `manual_capture/capture_status.json`

### Integrations to verify

Common types: ServiceNow, Slack, REST/Generic, outbound webhooks. Cross-reference `alert_rules_inventory.json` and `outbound_webhooks_inventory.json` for hints — do not duplicate secrets.

### SSO constants (Splunk On-Call standard)

| Setting | Value |
| :--- | :--- |
| ACS / Reply URL | `https://sso.victorops.com/sp/ACS.saml2` |
| Entity ID | `victorops.com` |
| Relay state | `https://portal.victorops.com/auth/sso/{org_slug}` |

SSO backend config is coordinated with Splunk support; document IdP-side settings only.

### Security

- Never commit API keys, webhook signatures, integration credentials, or SAML metadata
- Store secrets in a vault; reference paths in templates only
- `inventory/`, `manual_capture/`, `.env` are gitignored

---

## Phase 3: Apply (core v1)

`apply.py` provisions a target org from `inventory/` using `inventory/remapping.json`.

### Environment

```
TARGET_SPLUNK_ONCALL_API_ID
TARGET_SPLUNK_ONCALL_API_KEY
TARGET_SPLUNK_ONCALL_ORG_SLUG
```

### Commands

```bash
python3 apply.py           # dry-run (default)
python3 apply.py --apply   # execute writes
```

### Apply order

```mermaid
flowchart LR
    users[Users] --> teams[Teams]
    teams --> members[Members]
    members --> rotations[Rotations]
    rotations --> policies[EscalationPolicies]
    policies --> routingKeys[RoutingKeys]
    routingKeys --> alertRules[AlertRules]
```

| Step | API | Notes |
| :--- | :--- | :--- |
| Users | `POST /user` | Remap usernames; skip `null` entries |
| Teams | `POST /team` | Capture returned slug (API-assigned) |
| Members | `POST /team/{slug}/members` | After users and teams exist |
| Admins | — | **No public POST API** — configure in target UI |
| Rotations | `POST /teams/{team}/rotations` | Map source `rtg-*` slugs via label after create |
| Escalation policies | `POST /policies` | **Immutable after create via API** — includes full steps |
| Routing keys | `POST /org/routing-keys` | Target policy slugs from apply step |
| Alert rules | `POST /alertRules` | Preserve `rank`; remap routing-key matches |

### Deferred in core v1

Contact methods, paging policies, outbound webhooks, active overrides, integrations, SSO.

### Remapping

`generate_remapping.py` produces six categories: `users`, `teams`, `routing_keys`, `escalation_policies`, `alert_rules`, `outbound_webhooks`. Output defaults to `inventory/remapping.json`. Set any value to `null` to skip that resource. Re-running the generator overwrites the file.

Validate before apply:

```bash
python3 validate_inventory.py
python3 validate_apply.py
```

---

## Validation checklist

After discovery run:

- [ ] `python3 validate_inventory.py` passes
- [ ] All teams in `teams_inventory` have entries in `team_members`, `team_admins`, `rotation_definitions`, `schedules`
- [ ] Every policy slug in routing key targets appears in `escalation_policy_details`
- [ ] `discovery_metadata.json` counts and `files_written` match on-disk files
- [ ] Zero HTTP 404s on required endpoints in `discovery_run.log`
- [ ] Unit tests pass

Before apply:

- [ ] `python3 generate_remapping.py` run (or `inventory/remapping.json` manually maintained)
- [ ] `python3 validate_apply.py` passes
- [ ] `python3 apply.py` dry-run reviewed

After manual capture:

- [ ] Every enabled integration tile has a JSON file in `manual_capture/integrations/`
- [ ] Global admins recorded; team admins spot-checked against API inventory
- [ ] IdP SSO documented with correct relay state for org slug
- [ ] `capture_status.json` all items `complete`

---

## Handoff prompt (copy to another LLM)

```
You are continuing a Splunk On-Call (VictorOps) configuration migration project.

Goal: Complete master reference of source org config before access ends.
Scope now: API discovery (done) + manual capture (pending) + apply (core v1 implemented).

Repo contains:
- discovery.py, validate_inventory.py, generate_remapping.py, validate_apply.py, apply.py, env_loader.py
- manual_capture/ — templates for integrations, permissions, SSO (operator fill-in)
- tests/ — mocked unit tests
- docs/ — MIGRATION_GUIDE.md, VALIDATION_REPORT.md
- .env.example — credential template

Read docs/MIGRATION_GUIDE.md and README.md first. inventory/ and manual_capture/ are gitignored.

Constraints:
- Read-only discovery; no writes to Splunk On-Call
- Never commit secrets
- schedules_inventory = calendar projection; rotation_definitions_inventory = durable config
- Integrations have no public list API

First task: Review the existing code and project structure against Python and API-client best practices. Report:
1. Structural or design issues
2. Opportunities to simplify (remove duplication, reduce complexity, clearer abstractions)
3. Opportunities to improve (error handling, test coverage, performance, maintainability)
4. What to leave alone — do not suggest changes for their own sake

Prioritize high-impact, low-risk recommendations. Then ask which phase to continue: manual capture completion, apply hardening (deferred resources), or implementation of approved improvements.
```

---

## References

- [VictorOps public API docs](https://portal.victorops.com/public/api-docs.html)
- [Splunk On-Call SSO documentation](https://help.splunk.com/en/splunk-enterprise/alert-and-respond/splunk-on-call/introduction-to-splunk-on-call/single-sign-on)
