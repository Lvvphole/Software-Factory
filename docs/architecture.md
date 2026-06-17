# Architecture

## Control loop

`signal -> triage -> planning -> executor-router -> coding -> testing -> review -> security -> documentation -> verifier -> memory`

Every stage emits structured JSON and is logged. The **verifier** runs last and is the only stage permitted to declare COMPLETE or FAIL. The coding agent's self-assessment is recorded but ignored by the verifier.

v1.1 adds an **executor layer** between agents and the work they perform. Agents are executor-agnostic; the workflow selects the executor (`mock` by default, `claude_code` for real runs) and the verifier adjusts grading mode accordingly. See `executors.md`.

## Modules

| Module | Responsibility |
|---|---|
| `signals/` | Load + validate external signals |
| `triage/` | Classify severity, scope, security relevance |
| `planning/` | Produce step plan from triaged signal |
| `router/` | Select provider (mock / openai-compat / anthropic-compat / local) + log decision |
| `executors/` | **v1.1** — substrate that performs work. `mock` (no-op) and `claude_code` (subprocess to `claude -p`). |
| `agents/coding/` | Draft change intent (non-authoritative) |
| `agents/testing/` | Emit test plan + status |
| `agents/review/` | Static review findings |
| `agents/security/` | Secret + risk pattern scan |
| `agents/documentation/` | Identify doc updates |
| `workflows/` | Orchestrate stages; write artifacts; invoke verifier |
| `governance/` | Autonomy gating; block destructive/unsafe actions |
| `memory/` | Persist runs to SQLite |
| `integrations/` | External channel stubs (no v1 network calls) |
| `utils/` | Logging, IDs, JSON IO |
| `factory_cli/` | CLI entrypoint |

## Artifacts per run

Stored under `.factory-runs/{run_id}/` — see README. The set is fixed; the verifier checks the set mechanically.

## Boundaries (v1)

- No live model calls (mock provider is the only one that returns content; others raise without credentials).
- No real file edits (dry-run intent only).
- No production deploys (governance blocks by name).
- No destructive shell (governance blocks by pattern).

## v1.2 — Iteration on failure

After the testing agent runs, if (a) executor is non-mock, (b) a target_repo is set, (c) real tests failed, (d) `attempts_used < max_attempts`, and (e) governance allows, the workflow re-invokes the coding agent with a structured **failure_context**:

```json
{
  "attempt_number": 1,
  "previous_attempts": [
    {
      "attempt": 0,
      "diff_size_bytes": 240,
      "files_touched": ["src/calc.py"],
      "test_cmd": ["python", "-m", "pytest", "-q"],
      "test_exit_code": 1,
      "test_stdout_tail": "...",
      "test_stderr_tail": "..."
    }
  ]
}
```

The coding agent embeds this into the executor prompt (prefixed with `PREVIOUS ATTEMPT FAILED — this is attempt #N.`). Each attempt writes `attempt-{n}-coding-report.json` and `attempt-{n}-test-report.json`. The final attempt is mirrored to `coding-report.json` / `test-report.json` for backward compatibility. The whole loop is summarized in `iteration-report.json`.

The verifier still grades the **final** attempt only: `pass` requires real `tests_exit_code == 0`, non-empty diff, all artifacts present. Mock executor still runs exactly one attempt (no retry).
