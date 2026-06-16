# Runbook

## Operate

### Run a factory cycle

```bash
bash scripts/run-factory.sh examples/sample-signal.json
# or
factory run --signal examples/sample-signal.json --autonomy 2
```

Outputs land in `.factory-runs/{run_id}/`. The CLI prints `verifier_decision`; exit code is `0` on `pass`, `2` on `fail`, `1` on uncaught error.

### Inspect a run

```bash
cat .factory-runs/<run_id>/final-summary.md
cat .factory-runs/<run_id>/verifier-report.json
```

### Query memory

```bash
sqlite3 .factory-memory/factory.db "SELECT run_id, verifier_decision FROM runs ORDER BY started_at DESC LIMIT 10;"
```

## Extending

### Add an agent

1. Create `src/agents/<name>/__init__.py` with a `run(plan, ...)` returning JSON.
2. Wire it into `src/workflows/__init__.py` and add an artifact filename.
3. Append the filename to `REQUIRED_ARTIFACTS`.
4. Add a unit test under `tests/`.

### Add a model provider

See `docs/model-router.md` → "Adding a provider".

### Add a workflow

For v1 there is one workflow (`run_factory`). New workflows live as functions in `src/workflows/` and get CLI subcommands in `src/factory_cli/main.py`.

### Add a governance rule

See `docs/governance.md` → "Adding rules".

## Failure handling

Every failure should leave evidence:

- Uncaught CLI error → stderr line `factory: ERROR: ...`, exit 1.
- Verifier fail → `verifier-report.json` with `decision="fail"` and per-check booleans.
- Test failure → pytest non-zero exit; CI should publish the report.
- Governance block → entry in `run_record.governance_decisions` with `allowed=false`.

## Production deploys

**Not automated in v1.** `production_deploy` is in `BLOCKED_ACTIONS` and rejected by governance with `requires_human_approval=true`. A human must run the deploy out-of-band.
