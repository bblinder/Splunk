# Splunk On-Call Migration Tools

Migrate Splunk On-Call (VictorOps) configuration from a source org to a target org using discovered inventory and remapping.

## Pipeline

| Step | Script | Output |
|------|--------|--------|
| 1. Discovery | `discovery.py` | `inventory/*.json`, `inventory_summary.md` |
| 2. Inventory validation | `validate_inventory.py` | Exit 0/1 — consistency checks |
| 3. Remapping | `generate_remapping.py` | `inventory/remapping.json` |
| 4. Pre-flight | `validate_apply.py` | Exit 0/1 — remapping integrity |
| 5. Apply | `apply.py` | `inventory/apply_report.json` |

Manual capture (integrations, SSO, global admins) is documented in [`manual_capture/README.md`](manual_capture/README.md) and is not required for core usage.

## Setup

```bash
# Option A: venv + pip
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Option B: uv
uv venv && uv pip install -r requirements.txt

cp .env.example .env   # then edit with your credentials
```

Scripts load `.env` from the project root automatically (not dependent on the current working directory).

**Source (discovery)** — `discovery.py`:
```bash
SOURCE_SPLUNK_ONCALL_API_ID=...
SOURCE_SPLUNK_ONCALL_API_KEY=...
SOURCE_SPLUNK_ONCALL_ORG_SLUG=...
```

**Target (apply)** — `apply.py`:
```bash
TARGET_SPLUNK_ONCALL_API_ID=...
TARGET_SPLUNK_ONCALL_API_KEY=...
TARGET_SPLUNK_ONCALL_ORG_SLUG=...
```

**NOTE:** Shell `export` values take precedence over `.env`.

## Usage

```bash
# 1. Export source org (~30–40 min for large orgs)
python3 discovery.py

# 2. Validate inventory consistency
python3 validate_inventory.py

# 3. Generate remapping template (backs up edits if re-run!)
python3 generate_remapping.py
# Edit inventory/remapping.json — set null to skip a resource

# 4. Validate remapping before touching target
python3 validate_apply.py

# 5. Dry-run apply (default — no writes)
python3 apply.py

# 6. Execute apply
python3 apply.py --apply
```

With uv project venv: prefix commands with `uv run` (e.g. `uv run python3 discovery.py`).  
**NOTE:** Without a venv: `uv run --with requests python3 discovery.py` works for any script.

If you have an older `manual_capture/remapping.json`, copy it once: `cp manual_capture/remapping.json inventory/remapping.json`

## Remapping categories

`inventory/remapping.json` maps source identifiers to target names/slugs (or use`null` to skip specific resources):

- `users`, `teams`, `routing_keys`, `escalation_policies`, `alert_rules`, `outbound_webhooks`

Re-running `generate_remapping.py` **overwrites** the file. _Back up manual edits first._

## Apply scope (core usage)

**Included:** users, teams, members, rotations, escalation policies, routing keys, alert rules.

**Deferred:** contact methods, paging policies, outbound webhooks, active overrides, integrations, SSO.

**Manual after apply:** team admins (no public POST API).

Escalation policies are **immutable via API after creation**: dry-run and validate carefully before `--apply`.

## Tests

```bash
python3 -m unittest discover -s tests -t . -v
# uv: uv run python3 -m unittest discover -s tests -t . -v
```

## Deep reference

See [`docs/MIGRATION_GUIDE.md`](docs/MIGRATION_GUIDE.md) for inventory schema, API notes, and validation checklists.

[`docs/VALIDATION_REPORT.md`](docs/VALIDATION_REPORT.md) is a template for recording post-discovery validation results.
