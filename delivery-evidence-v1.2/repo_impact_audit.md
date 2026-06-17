# Repo Impact Audit — v1.2 (iteration on failure)

**Branch:** `feat/iteration-on-failure`
**Base:** v1.1.3 on `main` (07d4f94)
**Inventory size:** 81 files

## Summary

| Bucket | Count |
|---|---|
| MODIFIED | 8 |
| TESTED | 2 |
| UNCHANGED | 35 |
| IRRELEVANT | 36 |
| **ADDED (new)** | 6 |

## MODIFIED (8)

| File | Rationale |
|---|---|
| `README.md` | v1.2 quickstart + status update |
| `docs/architecture.md` | v1.2 retry control flow |
| `docs/executors.md` | v1.2 failure_context contract |
| `docs/runbook.md` | v1.2 ops + tuning --max-attempts |
| `src/agents/coding/__init__.py` | v1.2 accepts failure_context, builds retry prompt |
| `src/factory_cli/main.py` | v1.2 --max-attempts flag |
| `src/memory/__init__.py` | v1.2 persists attempts_count + final outcome |
| `src/workflows/__init__.py` | v1.2 retry loop in workflow |

## TESTED (2)

| File | Rationale |
|---|---|
| `tests/test_factory_run.py` | mock-no-retry invariant (updated) |
| `tests/test_workflow_v1_1.py` | per-attempt artifacts assertion (updated) |

## UNCHANGED (35)

| File | Rationale |
|---|---|
| `.env.example` | not in v1.2 surface |
| `.gitignore` | not in v1.2 surface |
| `LICENSE` | not in v1.2 surface |
| `docs/autonomy-levels.md` | not in v1.2 surface |
| `docs/governance.md` | not in v1.2 surface |
| `docs/memory.md` | not in v1.2 surface |
| `docs/model-router.md` | not in v1.2 surface |
| `examples/demo-signal.json` | default |
| `pyproject.toml` | default |
| `scripts/dev.sh` | script unchanged |
| `scripts/run-factory.sh` | script unchanged |
| `scripts/test.sh` | script unchanged |
| `src/agents/documentation/__init__.py` | v1.1 module untouched |
| `src/agents/review/__init__.py` | v1.1 module untouched |
| `src/agents/security/__init__.py` | v1.1 module untouched |
| `src/agents/testing/__init__.py` | v1.1 module untouched |
| `src/executors/__init__.py` | v1.1 module untouched |
| `src/executors/base.py` | v1.1 module untouched |
| `src/executors/claude_code/__init__.py` | v1.1 module untouched |
| `src/executors/mock/__init__.py` | v1.1 module untouched |
| `src/factory_cli/__init__.py` | v1.1 module untouched |
| `src/governance/__init__.py` | v1.1 module untouched |
| `src/integrations/__init__.py` | v1.1 module untouched |
| `src/planning/__init__.py` | v1.1 module untouched |
| `src/router/__init__.py` | v1.1 module untouched |
| `src/signals/__init__.py` | v1.1 module untouched |
| `src/triage/__init__.py` | v1.1 module untouched |
| `src/utils/__init__.py` | v1.1 module untouched |
| `tests/_stub_claude.py` | v1.1 test untouched |
| `tests/conftest.py` | v1.1 test untouched |
| `tests/test_executor_claude_code.py` | v1.1 test untouched |
| `tests/test_executor_mock.py` | v1.1 test untouched |
| `tests/test_governance.py` | v1.1 test untouched |
| `tests/test_memory.py` | v1.1 test untouched |
| `tests/test_router.py` | v1.1 test untouched |

## IRRELEVANT (36)

| File | Rationale |
|---|---|
| `.conflict-backup/README.md.original` | historical evidence / example dir |
| `delivery-evidence-v1.1/coding-diff.real.patch` | historical evidence / example dir |
| `delivery-evidence-v1.1/coding-report.real.json` | historical evidence / example dir |
| `delivery-evidence-v1.1/file-tree.txt` | historical evidence / example dir |
| `delivery-evidence-v1.1/final-summary.real.md` | historical evidence / example dir |
| `delivery-evidence-v1.1/memory-evidence.json` | historical evidence / example dir |
| `delivery-evidence-v1.1/mock-run-log.txt` | historical evidence / example dir |
| `delivery-evidence-v1.1/model-routing-log.real.json` | historical evidence / example dir |
| `delivery-evidence-v1.1/real-run-log.txt` | historical evidence / example dir |
| `delivery-evidence-v1.1/success-criteria-audit.md` | historical evidence / example dir |
| `delivery-evidence-v1.1/test-log.txt` | historical evidence / example dir |
| `delivery-evidence-v1.1/test-report.real.json` | historical evidence / example dir |
| `delivery-evidence-v1.1/verifier-report.real.json` | historical evidence / example dir |
| `delivery-evidence/PR-body.md` | historical evidence / example dir |
| `delivery-evidence/commit-hash.txt` | historical evidence / example dir |
| `delivery-evidence/factory-run-log.txt` | historical evidence / example dir |
| `delivery-evidence/file-tree.txt` | historical evidence / example dir |
| `delivery-evidence/final-summary.md` | historical evidence / example dir |
| `delivery-evidence/git-status-before.txt` | historical evidence / example dir |
| `delivery-evidence/governance-evidence.json` | historical evidence / example dir |
| `delivery-evidence/install-log.txt` | historical evidence / example dir |
| `delivery-evidence/memory-evidence.json` | historical evidence / example dir |
| `delivery-evidence/model-routing-log.json` | historical evidence / example dir |
| `delivery-evidence/push-instructions.md` | historical evidence / example dir |
| `delivery-evidence/success-criteria-audit.md` | historical evidence / example dir |
| `delivery-evidence/test-log.txt` | historical evidence / example dir |
| `delivery-evidence/verifier-report.json` | historical evidence / example dir |
| `examples/demo-target/.gitignore` | historical evidence / example dir |
| `examples/demo-target/README.md` | historical evidence / example dir |
| `examples/demo-target/conftest.py` | historical evidence / example dir |
| `examples/demo-target/pyproject.toml` | historical evidence / example dir |
| `examples/demo-target/src/calculator/__init__.py` | historical evidence / example dir |
| `examples/demo-target/tests/test_calculator.py` | historical evidence / example dir |
| `examples/sample-factory-run.json` | historical evidence / example dir |
| `examples/sample-plan.json` | historical evidence / example dir |
| `examples/sample-signal.json` | historical evidence / example dir |

## ADDED (6 new files)

| File | Rationale |
|---|---|
| `delivery-evidence-v1.2/repo_file_inventory.json` | criterion 1 |
| `delivery-evidence-v1.2/repo_impact_audit.md` | criterion 2 (this file) |
| `delivery-evidence-v1.2/success-criteria-audit.md` | evidence map |
| `delivery-evidence-v1.2/pytest.log` | test log |
| `tests/test_iteration_on_failure.py` | criterion 16 |
| `tests/_iteration_stub.py` | shared retry-aware stub |
