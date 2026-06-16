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
