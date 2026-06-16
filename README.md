# Software Factory (v1)

A coding-agent system that converts external software signals into planned, built, tested, reviewed, secured, documented, shipped, and memory-backed software changes through a verifier-controlled control loop.

**v1 scope is dry-run.** No real file edits, no live model calls, no production deploys. Every stage emits structured JSON; the verifier (not the coding agent) decides outcomes.

## Quickstart

```bash
bash scripts/dev.sh                                    # install
bash scripts/test.sh                                   # run tests
bash scripts/run-factory.sh examples/sample-signal.json # execute a run
# or:
factory run --signal examples/sample-signal.json
```

Each run writes artifacts to `.factory-runs/{run_id}/`:

```
signal.json  triage.json  plan.json  model-routing-log.json
coding-report.json  test-report.json  review-report.json
security-report.json  documentation-report.json
verifier-report.json  final-summary.md
```

## Architecture (at a glance)

```
signal -> triage -> planning -> router
                                 |
                                 v
       coding -> testing -> review -> security -> documentation
                                 |
                                 v
                            VERIFIER (authoritative)
                                 |
                                 v
                            memory (SQLite)
```

See `docs/architecture.md` for detail. The verifier is the sole authority on COMPLETE/FAIL — the coding agent's self-assessment is non-authoritative by design.

## Layout

```
src/
  signals/  triage/  planning/  router/  workflows/
  agents/{coding,testing,review,security,documentation}/
  memory/  governance/  integrations/  utils/  factory_cli/
docs/    examples/    scripts/    tests/
```

## Docs

- `docs/architecture.md` — system shape
- `docs/autonomy-levels.md` — 0..3 with v1 cap at 2
- `docs/governance.md` — blocked actions, approval rules
- `docs/model-router.md` — providers, selection, fallback
- `docs/memory.md` — SQLite schema, run records
- `docs/runbook.md` — operating procedures

## Extending

How to add agents, models, workflows, governance rules: see `docs/runbook.md` (Extending).

## Status

v1 dry-run. Not for production execution.
