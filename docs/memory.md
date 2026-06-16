# Memory

SQLite-backed persistence of factory runs. Default path: `.factory-memory/factory.db` (override with `FACTORY_DB_PATH`).

## Schema

```sql
CREATE TABLE runs (
  run_id            TEXT PRIMARY KEY,
  signal_id         TEXT,
  plan_id           TEXT,
  started_at        TEXT,
  completed_at      TEXT,
  verifier_decision TEXT,
  payload_json      TEXT NOT NULL
);
CREATE INDEX idx_runs_signal ON runs(signal_id);
```

`payload_json` holds the full run record (reports, governance decisions, etc.) for replay.

## API

- `persist_run(record, db_path=None) -> run_id`
- `fetch_run(run_id, db_path=None) -> dict | None`
- `count_runs(db_path=None) -> int`

## Memory file (per loop contract)

### COMPLETED_LAST_RUN
- Recorded fields: `run_id`, `started_at`/`completed_at`, `verifier_decision`, generated artifacts (via `.factory-runs/{run_id}/`), `test_report.overall`, `security_report.overall`, governance decision count, router supported providers.

### IN_PROGRESS
- Recorded mid-run via stage logs (`signals`, `triage`, `planning`, `router`, agent loggers).

### BLOCKERS
- Verifier `artifact_checks` and `*_ok` flags surface blockers.

### NEXT_ACTIONS
- Derived from verifier `decision=fail` + which checks failed.

### KNOWN_FAILURE_PATTERNS
- See contract; each is covered by either a verifier check or a test.
