# Splunk On-Call Migration Tools

This toolset facilitates the migration of Splunk On-Call (VictorOps) configurations from a source organization to a target organization using an automated inventory discovery and remapping workflow.

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

**Source Credentials (`discovery.py`):**
```bash
SOURCE_SPLUNK_ONCALL_API_ID=...
SOURCE_SPLUNK_ONCALL_API_KEY=...
SOURCE_SPLUNK_ONCALL_ORG_SLUG=...
```

**Target Credentials (`apply.py`):**
```bash
TARGET_SPLUNK_ONCALL_API_ID=...
TARGET_SPLUNK_ONCALL_API_KEY=...
TARGET_SPLUNK_ONCALL_ORG_SLUG=...
```

## Migration Workflow

Follow these steps in order to migrate your configuration:

1. **Discovery**: Extract the source organization state.
   `python3 discovery.py` (Expected duration: ~30–40 min for large orgs)
2. **Validation**: Verify consistency of the discovered inventory.
   `python3 validate_inventory.py`
3. **Remapping**: Generate a template for mapping source IDs to target names/slugs.
   `python3 generate_remapping.py`
   *Note: Edit `inventory/remapping.json` manually if needed. Set values to `null` to skip resources. Alert rules that match routing-key patterns may reference values not in `routing_keys_inventory`; add those keys to `remapping.json` manually or set the rule ID to `null` to skip.*
4. **Pre-flight**: Validate the remapping logic before executing against the target.
   `python3 validate_apply.py`
5. **Dry Run**: Perform a simulated application of changes (no writes).
   `python3 apply.py`
6. **Apply**: Execute the migration to the target organization.
   `python3 apply.py --apply`

**uv:** Prefix commands with `uv run`. Without a venv: `uv run --with requests python3 <script>.py`.

## Safety & Important Notes

- **Dry Runs**: Always run `python3 apply.py` without the `--apply` flag first to verify your changes.
- **Immutable Resources**: Escalation policies are **immutable via API after creation**. Validate your remapping carefully before running with `--apply`.
- **Overwrites**: Running `generate_remapping.py` will overwrite `inventory/remapping.json`. Back up any manual edits before re-running.

## Scope & Reference

### Included Resources
The migration covers the following core resources:
- `users`, `teams`, `members`, `rotations`, `escalation_policies`, `routing_keys`, `alert_rules`

### Deferred / Manual Tasks
The following are excluded from the automated run and may require manual handling or separate scripts:
- **Deferred:** `contact_methods`, `paging_policies`, `outbound_webhooks`, `active_overrides`, `integrations`, `SSO`.
- **Manual:** Team admins (no public POST API).

### Documentation
- **Migration Guide**: [`docs/MIGRATION_GUIDE.md`](docs/MIGRATION_GUIDE.md) (Schema, API notes, checklists)
- **Validation Template**: [`docs/VALIDATION_REPORT.md`](docs/VALIDATION_REPORT.md) (Template for recording results)

## Tests
```bash
python3 -m unittest discover -s tests -t . -v
# uv: uv run python3 -m unittest discover -s tests -t . -v
```
