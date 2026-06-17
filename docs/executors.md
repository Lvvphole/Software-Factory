# Executors (v1.1)

The executor layer is what actually performs work for an agent stage. v1.1 ships two:

| Executor      | What it does                                                   | Requires                                    |
|---------------|----------------------------------------------------------------|---------------------------------------------|
| `mock`        | No-op. Returns a synthesized result. Default for CI.            | nothing                                     |
| `claude_code` | Spawns `claude --print --bare …` in the target repo.            | `claude` on PATH, `ANTHROPIC_API_KEY` in env |

Agents are executor-agnostic. They call `get_executor(name).invoke(...)` and consume an `ExecutorResult`.

## When the verifier grades differently

| Executor      | grading_mode | `pass` iff                                                  |
|---------------|--------------|-------------------------------------------------------------|
| `mock`        | `artifact`   | all 11 artifacts present AND synthetic tests pass AND security pass |
| `claude_code` | `capability` | all 11 artifacts present AND real `tests_exit_code == 0` AND diff non-empty |

The coding agent's self-assessment is **always** ignored. The verifier is the only authority on COMPLETE/FAIL.

## CI-safe by default

Running

```
factory run --signal examples/sample-signal.json
```

uses the mock executor and requires no API key. CI never hits the network.

## Real run

```
export ANTHROPIC_API_KEY=...
factory run \
  --signal examples/demo-signal.json \
  --target-repo examples/demo-target \
  --executor claude_code
```

Pre-flight will refuse a target_repo that:

- doesn't exist
- isn't a git repo
- is on a protected branch (`main`/`master`/`production`/`release`) — override with `--allow-protected-branch`
- has uncommitted changes — override with `--allow-dirty`

The diff produced is left **uncommitted in the target repo's working tree** and also written to `.factory-runs/{run_id}/coding-diff.patch`. The user decides whether to commit/PR/discard.

## ExecutorResult shape

```python
@dataclass
class ExecutorResult:
    executor: str            # "mock" | "claude_code"
    exit_code: int           # 0 = ok
    duration_ms: int
    stdout: str              # tail
    stderr: str              # tail
    diff_size_bytes: int     # from git diff HEAD
    files_touched: list[str]
    model_used: str | None   # surfaced from claude -p json output when available
    cost_usd: float
    error: str | None
    raw: dict                # executor-specific extras
```

## How `claude_code` is invoked

```
claude --print --bare --output-format json --max-turns N \
       --allowedTools "<comma-sep>" "<prompt>"
```

- `--bare` skips hooks, MCP, auto-memory, and skill discovery for reproducible CI runs.
- `cwd` is set to `target_repo` so edits land there.
- `ANTHROPIC_API_KEY` is passed through from the user's environment. The factory never reads, stores, or commits it.
- Default allowed tools: `Read`, `Edit`, `Write`, `Bash(git diff*)`, `Bash(git status*)`. No general shell.
- Set `FACTORY_MAX_TURNS` to cap agentic turns (default 8).

## Adding an executor

1. Subclass with `name: str` and `invoke(...) -> ExecutorResult`.
2. Register in `src/executors/__init__.py`.
3. Add a CLI choice in `src/factory_cli/main.py`.
4. Add tests under `tests/test_executor_<name>.py` — preferably using a stub binary so CI runs without credentials.

## Testing without a real `claude` binary

Set `CLAUDE_CODE_BIN` to a stub script. The integration tests in `tests/test_executor_claude_code.py` and `tests/test_workflow_v1_1.py` use this pattern. No API key needed.

## v1.2 — failure_context contract

When the workflow retries after failed real tests, the coding agent passes a `failure_context` dict to the executor through the prompt. Production executors (and CI-stub executors) should:

1. Detect retry via the sentinel `"PREVIOUS ATTEMPT FAILED"` at the head of the prompt.
2. Read prior attempts' diff stats, test command, exit code, stdout/stderr tails embedded in the prompt.
3. Respond by producing a different diff that addresses the failure mode.

The harness writes one full coding-report + test-report per attempt and a top-level `iteration-report.json`. The verifier only ever grades the final attempt.

Mock executor never iterates.
