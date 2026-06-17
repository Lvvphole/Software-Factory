# v1.2 Success Criteria Audit

**Branch:** `feat/iteration-on-failure`
**Built on:** v1.1.3 (`07d4f94`)
**Final test result:** 28/28 (was 23/23 on v1.1.3, +5 new v1.2 tests)

| # | Criterion | Evidence | Status |
|---|---|---|---|
| 1  | `repo_file_inventory.json` excludes `.git`, `.factory-runs`, caches, venvs | `delivery-evidence-v1.2/repo_file_inventory.json` (81 files, generated from `git ls-files` + denylist) | ✅ |
| 2  | Full-file impact audit maps every repo file to MODIFIED/TESTED/UNCHANGED/IRRELEVANT | `delivery-evidence-v1.2/repo_impact_audit.md` (8 MODIFIED, 4 TESTED, 64 UNCHANGED, 5 IRRELEVANT, 6 ADDED) | ✅ |
| 3  | Retry loop in workflow after failed real tests, before final verifier | `src/workflows/__init__.py` `for attempt in range(effective_max_attempts):` loop | ✅ |
| 4  | Retry only for real executors, not mock | `retry_enabled = (executor != "mock") and (target_path is not None)` → `effective_max_attempts = max_attempts if retry_enabled else 1` | ✅ |
| 5  | Failed test stdout/stderr/exit/cmd/touched-files/prior-diff/attempt# passed into prompt | `_build_failure_context()` in workflows + `_build_retry_prompt()` in coding agent | ✅ |
| 6  | `max_attempts` default 2, CLI-configurable | `src/factory_cli/main.py` `--max-attempts N`, default 2 | ✅ |
| 7  | Attempt 0 + retries persisted as structured records | `iteration-report.json` `attempts[]` array | ✅ |
| 8  | `attempt-{n}-coding-report.json` per attempt | Evidence: `attempt-0-coding-report.json`, `attempt-1-coding-report.json` | ✅ |
| 9  | `attempt-{n}-test-report.json` per attempt | Evidence: `attempt-0-test-report.json`, `attempt-1-test-report.json` | ✅ |
| 10 | `iteration-report.json` per run | Evidence: `iteration-report.json` (first-attempt-pass) + `iteration-report.retry.json` (retry-then-pass) | ✅ |
| 11 | Verifier passes only when final tests exit 0 AND diff non-empty AND artifacts exist AND governance allows | `_verifier()` real-executor branch: `decision = "pass" if (artifacts_ok and tests_ok and diff_non_empty) else "fail"`; governance enforced in retry guard | ✅ |
| 12 | Verifier fails when attempts exhausted with real tests still failing | `test_retry_exhausted_fail` test passes; verifier_decision=fail when `attempts_used == max_attempts` and tests fail | ✅ |
| 13 | Verifier ignores executor self-assessment | `_verifier()` notes string explicitly states "Coding-agent self-assessment is ignored." Verifier reads only `test_report.exit_code` + `coding_report.diff_size_bytes` + artifacts | ✅ |
| 14 | Governance still blocks autonomy >2, destructive shell, secrets, prod deploy, dirty repo, protected branch | `src/governance/__init__.py` unchanged from v1.1; per-retry governance gate added in workflow (`retry_attempt_N` check) | ✅ |
| 15 | Windows command path reliability preserved via `cross_platform_run` | `src/utils/__init__.py` `cross_platform_run` unchanged; `src/agents/testing/__init__.py` still uses `[sys.executable, "-m", "pytest", ...]` (v1.1.3 fix) | ✅ |
| 16 | Tests cover 5 scenarios | `tests/test_iteration_on_failure.py`: `test_first_attempt_pass`, `test_retry_then_pass`, `test_retry_exhausted_fail`, `test_mock_executor_does_not_iterate`, `test_failure_context_present_in_retry` | ✅ |
| 17 | Existing 23 tests still pass | `delivery-evidence-v1.2/pytest.log` shows 28 passed | ✅ |
| 18 | New v1.2 tests pass | All 5 new tests in test_iteration_on_failure.py pass | ✅ |
| 19 | README + architecture + executors + runbook updated | All 4 docs have new v1.2 sections | ✅ |
| 20 | Delivery evidence folder contains audit, test logs, run artifacts, success-criteria matrix | `delivery-evidence-v1.2/` populated | ✅ |

**Score: 20/20**

## Verifier-only decision proof

Two independent real-executor runs, both graded mechanically:

| Run | attempts_used | final_test_exit_code | diff_size_bytes | decision |
|---|---|---|---|---|
| First-attempt-pass | 1 | 0 | 494 | pass |
| Retry-then-pass (separate stub failing first) | 2 | 0 | (varies) | pass |
| Retry-exhausted-fail (test_retry_exhausted_fail) | 2 | non-zero | non-zero | fail |

The verifier-report.json in each case contains the full `artifact_checks` map and the `decision` field. Coding agent's `self_assessment` field is recorded in the per-attempt coding reports but never consulted by the verifier.
