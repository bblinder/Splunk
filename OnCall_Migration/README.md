# Splunk On-Call Migration Tools

A migration toolset for Splunk On-Call (VictorOps). Snapshot and migrate configurations from a source organization to a target organization using an automated inventory discovery and remapping workflow.

## Repository layout

```
OnCall_Migration/
├── README.md
├── requirements.txt
├── .env.example                  # copy to .env (gitignored)
├── discovery.py                  # step 1 — export source org
├── validate_inventory.py         # step 2
├── generate_remapping.py         # step 3
├── validate_apply.py             # step 4
├── apply.py                      # steps 5–6 (dry-run / --apply)
├── utils/
│   ├── env_loader.py
│   ├── rate_limiter.py
│   ├── exceptions.py
│   ├── migration_types.py
│   ├── summary_reporter.py
│   └── team_scope.py
├── docs/
│   ├── MIGRATION_GUIDE.md
│   ├── VALIDATION_REPORT.md
├── tests/
│   ├── test_discovery.py
│   ├── test_apply.py
│   └── …                         # other test_*.py modules
├── inventory/                    # gitignored — API export + remapping
│   ├── *_inventory.json
│   ├── discovery_metadata.json
│   ├── inventory_summary.md
│   ├── remapping.json
│   └── apply_report.json         # written after apply
├── manual_capture/               # templates tracked; integration JSON captures gitignored
│   ├── README.md
│   ├── capture_status.json
│   ├── integrations/
│   │   └── integration.example.json
│   ├── user_permissions/
│   └── sso/
└── discovery_run.log             # gitignored — discovery HTTP log
```

Paths marked **gitignored** (`inventory/`, `.env`, `discovery_run.log`, filled `manual_capture/integrations/*.json`) are local operator artifacts; back them up before source org access ends. **Do not commit secrets** in those paths.

## Quick Start

### Installation
You can install dependencies using either standard `venv` or `uv`:

```bash
# Option A: venv + pip
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Option B: uv
uv venv && uv pip install -r requirements.txt
```

### Configuration
Create a `.env` file in the project root (copy from `.env.example`) and provide the following credentials. Scripts load `.env` from the project root automatically; shell `export` values override file settings.

**Source Credentials (used by `discovery.py`):**
```bash
SOURCE_SPLUNK_ONCALL_API_ID=...
SOURCE_SPLUNK_ONCALL_API_KEY=...
SOURCE_SPLUNK_ONCALL_ORG_SLUG=...
```

**Target Credentials (used by `apply.py`):**
```bash
TARGET_SPLUNK_ONCALL_API_ID=...
TARGET_SPLUNK_ONCALL_API_KEY=...
TARGET_SPLUNK_ONCALL_ORG_SLUG=...
```

## Migration Workflow

Follow these steps in order to migrate your Splunk On-Call configuration:

1. **Discovery**: Extract the source organization state.
   `python3 discovery.py` (Expected duration: ~30–40 min for large orgs). For partial exports, pass team **slugs**: `python3 discovery.py --teams sabre-a,sabre-b,sabre-c` or `--teams-file inventory/team_scope.txt`.
2. **Validation**: Verify consistency of the discovered inventory.
   `python3 validate_inventory.py`
3. **Remapping**: Generate a template for mapping source IDs to target names/slugs.
   `python3 generate_remapping.py`
   *Note: Edit `inventory/remapping.json` manually if needed. **Set values to `null` to skip resources**. Remap email addresses under `emails` when the target org uses different domains. Alert rules that match routing-key patterns may reference values not in `routing_keys_inventory`; add those keys to `remapping.json` manually or set the rule ID to `null` to skip.*
4. **Pre-flight**: Validate the remapping logic before executing against the target.
   `python3 validate_apply.py`
5. **Dry Run**: Perform a simulated application of changes (no writes).
   `python3 apply.py`
6. **Apply**: Execute the migration to the target organization.
   `python3 apply.py --apply`

Optional path flags: `--inventory` (default `inventory`), `--remapping` (default `inventory/remapping.json`) on `generate_remapping.py`, `validate_apply.py`, and `apply.py`; `--inventory` on `discovery.py` and `validate_inventory.py`; `--teams` / `--teams-file` on `discovery.py` for scoped exports. See the Migration Guide CLI reference.

All pipeline scripts accept `-h` / `--help` for flags and defaults. See [`docs/MIGRATION_GUIDE.md`](docs/MIGRATION_GUIDE.md) for more detailed information on CLI/flags options.

**uv:** Prefix commands with `uv run`. Without a venv: `uv run --with requests python3 <script>.py`.

## Safety & Important Notes

- **Dry run first:** `python3 apply.py` (no `--apply`) simulates the migration and writes `inventory/apply_report.json` without changing the target org. Review that report before you run with `--apply`.
- **Escalation policies cannot be edited later:** Once created in the target org, policy steps and routing cannot be changed through the API. Double-check `inventory/remapping.json` and run `python3 validate_apply.py` before applying.
- **Re-running apply:** A second run is mostly safe for resources that already exist — users, teams, members, rotations, and escalation policies are skipped when found. Routing keys and alert rules are posted again and may fail or duplicate if they already exist. A policy created with wrong steps cannot be fixed by re-applying; fix it in the target UI or delete and recreate the policy manually, then adjust remapping if needed.
- **Overwrites:** Running `generate_remapping.py` overwrites `inventory/remapping.json`. Back up any manual edits before re-running.

## Scope & Reference

### Included Resources
The migration covers the following core resources:
- `users`, `teams`, `members`, `rotations`, `escalation_policies`, `routing_keys`, `alert_rules`

### Deferred / Manual Tasks
The following are excluded from the automated run and may require manual handling or separate scripts:
- **Deferred:** `contact_methods`, `paging_policies`, `outbound_webhooks`, `active_overrides`, `integrations`, `SSO`.
- **Manual:** Team admins (no public POST API).

### Documentation
- **Migration Guide**: [`docs/MIGRATION_GUIDE.md`](docs/MIGRATION_GUIDE.md) (Schema, API notes, checklists, repository layout)
- **Validation Template**: [`docs/VALIDATION_REPORT.md`](docs/VALIDATION_REPORT.md) (Template for recording results)
- **Support modules**: [`utils/`](utils/) — `env_loader`, `rate_limiter`, `exceptions`, `migration_types`, `summary_reporter`, `team_scope`

## Tests
```bash
python3 -m unittest discover -s tests -t . -v
# uv: uv run python3 -m unittest discover -s tests -t . -v
```
