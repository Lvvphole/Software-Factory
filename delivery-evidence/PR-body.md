# Port v1 Software Factory Implementation

## Summary

Ports the v1 Software Factory dry-run implementation into this repo. The factory converts external software signals into planned, built, tested, reviewed, secured, documented, and memory-backed software changes through a **verifier-controlled** control loop.

**v1 scope is dry-run.** No real file edits, no live model calls, no production deploys.

## What's included

- **Lifecycle modules** (`src/`): `signals`, `triage`, `planning`, `router`, `agents/{coding,testing,review,security,documentation}`, `workflows`, `memory`, `governance`, `integrations`, `utils`, `factory_cli`
- **CLI**: `factory run --signal <path>` (entry point in `pyproject.toml`)
- **4-provider model router**: `mock` (default), `openai_compatible`, `anthropic_compatible`, `local_placeholder` — non-mock providers **raise rather than make hidden calls** without explicit credentials
- **SQLite memory layer**: `.factory-memory/factory.db`
- **Governance gates**: destructive shell, `production_deploy`, hardcoded secrets, autonomy_level > 2 — all blocked with evidence
- **Verifier**: owns the COMPLETE/FAIL decision. Coding-agent self-assessment is explicitly **ignored** per contract.
- **Tests**: 11 passing (pytest)
- **Docs**: `architecture.md`, `autonomy-levels.md`, `governance.md`, `model-router.md`, `memory.md`, `runbook.md`
- **Examples**: `sample-signal.json`, `sample-plan.json`, `sample-factory-run.json`
- **Scripts**: `scripts/{dev,test,run-factory}.sh`

## Verification (from this branch's checkout)

```bash
pip install -e .[dev]                                 # OK
bash scripts/test.sh                                  # 11 passed
factory run --signal examples/sample-signal.json      # verifier_decision: pass
```

All 11 required run artifacts written to `.factory-runs/{run_id}/`. SQLite memory persisted at `.factory-memory/factory.db`.

## Evidence

See `delivery-evidence/`:

- `success-criteria-audit.md` — maps all 30 port-contract criteria to evidence files
- `install-log.txt`, `test-log.txt`, `factory-run-log.txt`
- `verifier-report.json` (decision: pass), `final-summary.md`, `model-routing-log.json`
- `governance-evidence.json` (4 unsafe actions blocked)
- `memory-evidence.json` (SQLite persistence)
- `file-tree.txt`, `git-diff-stat.txt`, `commit-hash.txt`

## Constraints honored

- No history rewrite, no force-push
- `LICENSE` untouched; original 18-byte `README.md` preserved at `.conflict-backup/README.md.original`
- No real secrets committed (`.env.example` blank)
- Default execution uses mock router (no live model calls)
- Production deployment requires explicit human approval (governance block)
- Executor did not determine completion — verifier did

## Reviewer checklist

- [ ] `pip install -e .[dev]` runs clean
- [ ] `bash scripts/test.sh` → 11 passed
- [ ] `factory run --signal examples/sample-signal.json` → `verifier_decision: pass`
- [ ] `delivery-evidence/success-criteria-audit.md` shows ✅ on all 30 rows
- [ ] No unexpected files in diff
