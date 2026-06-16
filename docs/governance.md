# Governance

The governance module gates every agent action.

## Always-blocked actions

- `production_deploy` — requires explicit human approval; fully blocked in v1.
- `delete_production_data`
- `rotate_secrets_without_approval`

## Pattern blocks

- Destructive shell: `rm -rf /`, `mkfs.*`, `dd if=... of=/dev/*`, forkbomb, `sudo rm -rf`.
- Hardcoded secrets: OpenAI-shaped keys (`sk-…`), AWS access keys (`AKIA…`).

## Autonomy cap

`autonomy_level > 2` is rejected in v1 with `allowed=false`.

## Decision record

Every evaluation returns:

```json
{ "timestamp": "...", "action": {...}, "autonomy_level": 2,
  "allowed": true|false, "reason": "...", "requires_human_approval": false }
```

All decisions are logged via the structured logger and surfaced in the run's verifier report under `governance_ok`.

## Adding rules

Add to `BLOCKED_ACTIONS`, `DESTRUCTIVE_PATTERNS`, or `SECRET_PATTERNS` in `src/governance/__init__.py` and add a test in `tests/test_governance.py`.
