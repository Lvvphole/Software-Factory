# Software Factory (v1.1)

A coding-agent **harness** that converts external signals into planned, built, tested, reviewed, secured, documented, and memory-backed software changes. The harness owns lifecycle, governance, routing, memory, and the verifier; an **executor** (Claude Code by default in real runs; mock for CI) does the actual coding work.

> **v1.1 scope:** make exactly one end-to-end real run work — Claude Code edits a target repo, real tests run on the real diff, the verifier grades on capability (tests-pass + non-empty diff + artifacts) rather than artifact presence.

## Quickstart

### CI-safe (no API key required)

```bash
bash scripts/dev.sh                                # install
bash scripts/test.sh                               # 23 tests
factory run --signal examples/sample-signal.json   # mock executor, artifact grading
```

### Real run (Claude Code)

```bash
# Requirements: ANTHROPIC_API_KEY in env, `claude` (Claude Code CLI) on PATH
# Install Claude Code: npm i -g @anthropic-ai/claude-code

# Initialize the demo target as a git repo on a non-protected branch
cd examples/demo-target && git init -b feature/factory && \
  git add -A && git -c user.email=t@t -c user.name=t commit -m init
cd ../..

# Run
factory run \
  --signal examples/demo-signal.json \
  --target-repo examples/demo-target \
  --executor claude_code
```

The factory writes 11 artifacts plus `coding-diff.patch` (the real diff) to `.factory-runs/{run_id}/`. The diff is left **uncommitted** in the target repo's working tree — you decide whether to commit/PR/discard.

## How grading works

| Executor      | grading_mode | `pass` iff                                                       |
|---------------|--------------|------------------------------------------------------------------|
| `mock`        | `artifact`   | artifacts present AND synthetic tests pass AND security pass     |
| `claude_code` | `capability` | artifacts present AND **real** tests_exit_code == 0 AND non-empty diff |

The coding agent's self-assessment is always ignored. The verifier decides.

## Architecture

```
signal -> triage -> planning
                       |
                       v
            +---- executor router ----+
            |     mock | claude_code  |
            +-------------|-----------+
                          v
       coding -> testing -> review -> security -> documentation
                          |
                          v
                  VERIFIER (capability or artifact mode)
                          |
                          v
                    memory (SQLite)
```

See `docs/architecture.md`, `docs/executors.md`.

## Layout

```
src/
  signals/  triage/  planning/  router/  workflows/
  executors/{mock,claude_code}/         # v1.1
  agents/{coding,testing,review,security,documentation}/
  memory/  governance/  integrations/  utils/  factory_cli/
docs/    examples/{demo-target/,*.json}   scripts/    tests/
```

## Governance

- Pre-flight on every real run: target_repo must exist, be a git repo, on a non-protected branch, clean.
- Action gates: destructive shell, hardcoded secrets, `production_deploy`, autonomy > 2 — all blocked.
- See `docs/governance.md`.

## Docs

- `docs/architecture.md` — system shape
- `docs/executors.md` — **v1.1** executor layer
- `docs/autonomy-levels.md` — 0..3 with v1.1 cap at 2
- `docs/governance.md` — blocked actions, target-repo preflight
- `docs/model-router.md` — provider adapters
- `docs/memory.md` — SQLite schema (includes v1.1 migration)
- `docs/runbook.md` — operating procedures, including extending

## Status

v1.1 — Claude Code is the executor; harness owns the loop. No iteration-on-failure yet (deferred to v1.2). Default autonomy=2. No production-deploy automation.
