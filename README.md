# Software Factory (v1.4)

A coding-agent **harness** that converts external signals into planned, built, tested, reviewed, secured, documented, and memory-backed software changes — and can open a draft pull request for the result. The harness owns lifecycle, governance, routing, memory, and the **verifier** (the sole pass/fail authority); an **executor** (Claude Code by default in real runs; mock for CI) does the actual coding work.

The design philosophy: **evidence-first, governance-gated, model-independent.** The coding agent never grades its own work, stubs fail loudly rather than silently, and every side-effectful action is opt-in and gated.

## Version history

| Version | Capability |
|---|---|
| v1.1 | Real executor layer + capability verifier; Windows portability (`cross_platform_run`, `python -m pytest`) |
| v1.2 | Bounded **retry loop** — on real test failure, failure context is fed back to the executor and retried (`--max-attempts`) |
| v1.2.2 | Windows prompt path fixed — prompt piped via **stdin** (`claude -p`), never a shell-parsed positional |
| v1.3 | Robust executor JSON parse (model from `modelUsage`, actionable auth errors); diff hygiene (pyc/cache excluded); **real review/security/docs agents** that analyze the actual diff; **opt-in draft PR creation** |
| v1.4 | **Scoped, auditable security waivers** — a signal can authorize a specific finding without defeating the scanner |

## Quickstart

### CI-safe (no API key required)

```bash
bash scripts/dev.sh                                # install
bash scripts/test.sh                               # 68 tests
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
  --executor claude_code \
  --max-attempts 2            # v1.2: retry up to 2 attempts if tests fail
```

The factory writes the run artifacts plus `coding-diff.patch` (the real diff) to `.factory-runs/{run_id}/`. The diff is left **uncommitted** in the target repo's working tree — you decide whether to commit/PR/discard.

### Real run with draft PR (v1.3, opt-in)

```bash
# Requires GITHUB_TOKEN in env (fine-grained PAT: Contents + Pull requests
# write on the target repo). The target repo must have a GitHub origin.
factory run \
  --signal examples/demo-signal.json \
  --target-repo /path/to/repo-with-github-origin \
  --executor claude_code \
  --max-attempts 2 \
  --create-pr --pr-base main
```

PR creation is gated on ALL of: opt-in (`--create-pr`), a real target repo, **verifier decision == pass**, and governance approval. The factory opens a **draft** PR and **never merges**. The token is read from env only — never logged, never written to artifacts.

## How grading works

| Executor      | grading_mode | `pass` iff                                                       |
|---------------|--------------|------------------------------------------------------------------|
| `mock`        | `artifact`   | artifacts present AND synthetic tests pass AND security pass     |
| `claude_code` | `capability` | artifacts present AND **real** tests_exit_code == 0 AND non-empty diff AND security pass |

The coding agent's self-assessment is always ignored. The verifier decides.

## The agents (v1.3 — real analysis over the actual diff)

All three read the unified diff and scan **added lines only** (removing a problem doesn't trip the scanner; unchanged context isn't re-flagged). Deterministic, dependency-free, no LLM calls — they run on every factory run.

- **Review** (`overall in {pass, needs_changes}`, non-blocking) — flags TODO/FIXME, debug prints, bare `except:`, broad handlers, breakpoints, stubbed `pass`, over-long lines, large diffs, and source-changed-without-tests. Governance-blocked steps remain high-severity. High severity → `needs_changes`.
- **Security** (`overall in {pass, fail}`, **verifier-blocking**) — detects API keys, private keys, hardcoded credentials, and dangerous calls (`eval`/`exec`/`os.system`/`subprocess shell=True`/`pickle.loads`/`yaml.load`/`verify=False`/`#nosec`). Any unwaived critical/high → `fail`.
- **Documentation** (`overall == pass`, advisory) — detects public API changes vs. whether docs were updated; emits a `documentation_gap` + concrete recommendations.

## Security waivers (v1.4)

A signal can authorize a specific security finding without disabling the scanner:

```json
"security_waivers": [
  {
    "pattern_id": "shell-true",
    "file": "scripts/deploy.py",
    "reason": "deploy step needs a shell pipeline",
    "approved_by": "emory"
  }
]
```

Semantics (conservative by design):
- A waiver only **downgrades** a matched finding to `status: "waived"` — never hides it. Waived findings are recorded in `report["waived"]` with reason + approver. **Transparency over silent suppression.**
- A waiver must name a **specific** `pattern_id`. There is **no blanket waive-all**.
- `reason` and `approved_by` are **required**; a malformed waiver is ignored (finding stays active) and counted in `malformed_waivers`.
- Only **unwaived** critical/high issues block the run.

Stable pattern ids: `anthropic-openai-key`, `aws-access-key`, `private-key-block`, `github-pat`, `slack-token`, `hardcoded-credential`, `eval`, `exec`, `shell-true`, `os-system`, `pickle-loads`, `yaml-load`, `tls-verify-false`, `nosec-comment`.

## Architecture

```
signal -> triage -> planning
                       |
                       v
            +---- executor router ----+
            |     mock | claude_code  |   (prompt via stdin; model-independent)
            +-------------|-----------+
                          v
              coding  <--- bounded retry loop (v1.2)
                |          (failure context fed back on real test failure)
                v
             testing  (real: python -m pytest)
                |
                v
   review -> security -> documentation     (v1.3: real analysis over coding-diff.patch)
                          |                  security waivers applied here (v1.4)
                          v
                  VERIFIER (capability | artifact)   <- sole pass/fail authority
                          |
            (if pass + --create-pr + governance) -> draft PR (v1.3)
                          |
                          v
                    memory (SQLite)
```

See `docs/architecture.md`, `docs/executors.md`.

## Layout

```
src/
  signals/  triage/  planning/  router/  workflows/
  executors/{mock,claude_code}/              # claude_code pipes prompt via stdin
  agents/{coding,testing,review,security,documentation}/   # review/security/docs real (v1.3)
  integrations/github/                        # draft PR creation (v1.3, stdlib urllib)
  memory/  governance/  utils/  factory_cli/
docs/    examples/{demo-target/,*.json}   scripts/    tests/
```

## Governance

- Pre-flight on every real run: target_repo must exist, be a git repo, on a non-protected branch, clean (override with `--allow-dirty` / `--allow-protected-branch`).
- Action gates: destructive shell, hardcoded secrets, `production_deploy`, autonomy > 2 — all blocked.
- PR creation is a governed action — gated on verifier pass + autonomy level; draft-only, never merges.
- See `docs/governance.md`.

## CLI flags (run)

| Flag | Default | Purpose |
|---|---|---|
| `--signal` | (required) | path to signal JSON |
| `--target-repo` | none | repo the executor operates on (real runs) |
| `--executor` | `mock` | `mock` or `claude_code` |
| `--test-cmd` | none | e.g. `"python -m pytest -q"` |
| `--max-attempts` | 2 | retry budget on real test failure (v1.2) |
| `--allow-dirty` | off | bypass clean-tree preflight |
| `--allow-protected-branch` | off | bypass protected-branch preflight |
| `--create-pr` | off | open a draft PR if verifier passes (v1.3; needs `GITHUB_TOKEN`) |
| `--pr-base` | `main` | base branch for the PR |

## Docs

- `docs/architecture.md` — system shape
- `docs/executors.md` — executor layer
- `docs/autonomy-levels.md` — 0..3 with cap at 2
- `docs/governance.md` — blocked actions, target-repo preflight
- `docs/model-router.md` — provider adapters
- `docs/memory.md` — SQLite schema + migrations
- `docs/runbook.md` — operating procedures, including extending

## Status

v1.4 — bounded retry loop; Windows stdin prompt path; real review/security/docs agents over the actual diff; opt-in draft PR creation; scoped auditable security waivers. Default autonomy=2, default max_attempts=2. Draft-only PRs; no production-deploy automation. **68 tests.**

## Known gaps (tracked, not yet built)

- **Durable orchestration.** Runs are single-process and synchronous; there is no step-level checkpoint or crash-resume. This is intentional for operator-supervised Diagnostic/Pilot use. It becomes a real liability at the first **unattended, scheduled** run (e.g. a Retainer's weekly cadence), where a crash could orphan a run or duplicate a PR. Adopt a durable orchestrator (e.g. Inngest/Temporal or a checkpointed queue) before the first scheduled cadence.
- **Self-extension.** The factory consumes signals a human places; it does not author its own pipeline stages or schedule itself. Intentional, given the deterministic/auditable design goals.
