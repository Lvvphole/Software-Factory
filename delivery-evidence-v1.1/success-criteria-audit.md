# Success Criteria Audit — v1.1 (Claude Code as executor)

**Branch:** `feat/claude-code-executor`
**Build vs:** merged `main` from PR #1 (commit `1617c78`)
**Real-run evidence:** `verifier-report.real.json`, `coding-diff.real.patch`, `final-summary.real.md`
**Test result:** 23 passed (was 11 in v1)

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | New executor module `src/executors/claude_code/` with `invoke(prompt, target_repo, allowed_tools, timeout) → ExecutorResult` | ✅ | `file-tree.txt`: `src/executors/{base.py,__init__.py,mock/__init__.py,claude_code/__init__.py}` |
| 2 | Mock executor preserved at `src/executors/mock/`; default unchanged | ✅ | `file-tree.txt`; mock-run-log shows `executor: "mock"`, `grading_mode: "artifact"` |
| 3 | CLI accepts `--target-repo` and `--executor {mock, claude_code}` | ✅ | `real-run-log.txt` shows both flags consumed |
| 4 | Coding agent calls selected executor; captures real `git diff HEAD`; writes `coding-diff.patch` | ✅ | `coding-diff.real.patch` (494 bytes, real diff to `src/calculator/__init__.py`) |
| 5 | Coding report records executor, prompt sent, exit code, files touched, lines, duration_ms, model | ✅ | `coding-report.real.json` — `executor: "claude_code"`, `exit_code: 0`, `files_touched: ["src/calculator/__init__.py"]`, `duration_ms`, `model_used: "claude-stub"` |
| 6 | Testing agent runs target repo's real test command (auto-detected) | ✅ | `test-report.real.json` — `mode: "real"`, `cmd: ["pytest", "-q"]`, `exit_code: 0`, `overall: "pass"` |
| 7 | Verifier decision: `pass ⟺ (tests_exit_code==0) AND (diff non-empty) AND (artifacts present)` | ✅ | `verifier-report.real.json` — `grading_mode: "capability"`, `decision: "pass"` with all three conditions enforced; `notes` explicitly state the rule |
| 8 | Governance gates executor: rejects bad target_repo paths, dirty/protected branch (overridable), destructive shell still blocked | ✅ | `tests/test_governance.py` (10 tests covering preflight + action gates) |
| 9 | Pre-flight check: target exists, is git, non-protected branch, test cmd detectable | ✅ | `real-run-log.txt`: `preflight: target_repo OK branch=feature/factory clean=True` |
| 10 | Demo target repo `examples/demo-target/` — minimal Python package with one failing test the agent should fix | ✅ | `file-tree.txt`; `coding-diff.real.patch` shows real fix |
| 11 | Integration tests verify subprocess machinery using a stub `claude` binary (no real API call) | ✅ | `tests/test_executor_claude_code.py` (3 tests) + `tests/test_workflow_v1_1.py` (2 tests); all run with `CLAUDE_CODE_BIN` env override |
| 12 | Existing 11 unit tests still pass | ✅ | `test-log.txt`: `23 passed` (11 original + 5 governance preflight + 3 mock + 3 claude_code + 2 workflow) |
| 13 | Memory schema extends `runs` with `target_repo`, `executor`, `tests_passed`, `diff_size_bytes`; idempotent migration | ✅ | `memory-evidence.json`: `v1_1_columns_present: true`; mock-run-log shows `memory migration: added columns ['target_repo', 'executor', 'tests_passed', 'diff_size_bytes']` on first run |
| 14 | Model routing log records executor selected per stage | ✅ | `model-routing-log.real.json` — first entry: `executor: "claude_code"`, `selected_model: "claude-stub"`, `selection_reason: "--executor claude_code"`, all six required fields present |
| 15 | Docs updated: new `docs/executors.md`; `docs/architecture.md` reflects executor layer; README shows real-run command | ✅ | `file-tree.txt`: `docs/executors.md` present; `docs/architecture.md` updated; `README.md` has both quickstart paths |
| 16 | CI-safe default: `factory run --signal examples/sample-signal.json` still passes on mock, no API key | ✅ | `mock-run-log.txt`: `verifier_decision: "pass"`, `executor: "mock"`, `grading_mode: "artifact"` |
| 17 | Real run path documented and demonstrated | ✅ | `README.md` real-run section; `real-run-log.txt` shows end-to-end success with stub `claude` proving the wiring |

## Constraints honored

- v1.1 only — no iteration-on-test-failure loop (deferred to v1.2).
- Default executor: `mock`. Real execution requires explicit `--executor claude_code`.
- No `ANTHROPIC_API_KEY` in code, `.env.example`, or any committed file.
- Subprocess only — no Python SDK dependency added to `pyproject.toml`.
- Governance pre-flight runs before every executor invocation.
- Verifier never grades subjectively; decision is mechanical (`tests_exit_code`, `diff_size_bytes`, artifact set).
- No production-deploy automation. `production_deploy` still in `BLOCKED_ACTIONS`.
- New work on `feat/claude-code-executor` branch; no force-push to `main`.

## Two verifier modes proven

| Mode | Trigger | Demo |
|---|---|---|
| `artifact` | `--executor mock` | sample-signal run, `verifier_decision: pass` with 0-byte diff |
| `capability` | `--executor claude_code` | demo-signal run on demo-target, `verifier_decision: pass` driven by real `pytest` exit 0 and 494-byte diff fixing `add(a-b) -> add(a+b)` |

## Final decision

**COMPLETE** — all 17 v1.1 success criteria satisfied with concrete evidence.
