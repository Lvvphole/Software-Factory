"""Claude Code executor.

Wraps `claude` (Claude Code CLI) in headless mode. Subprocess is invoked with
`cwd=target_repo` so any file edits land in the target repo's working tree.
Diff is read after the call via `git diff HEAD`.

Required: `claude` on PATH, `ANTHROPIC_API_KEY` in env (or an apiKeyHelper
configured via --settings). Both come from the user's environment, never
from this codebase.

This module never touches the host system outside `target_repo` and the
subprocess it spawns. Governance pre-flight is the caller's responsibility.
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from ..base import ExecutorResult
from utils import cross_platform_run


class ClaudeCodeExecutor:
    name = "claude_code"
    binary = "claude"

    def _binary_path(self) -> str | None:
        # Respect CLAUDE_CODE_BIN override (used by tests with stub binary).
        override = os.environ.get("CLAUDE_CODE_BIN")
        if override:
            return override
        return shutil.which(self.binary)

    def _git(self, target_repo: Path, *args: str) -> str:
        return subprocess.check_output(
            ["git", *args], cwd=target_repo, text=True, stderr=subprocess.PIPE
        ).strip()

    def _diff_stats(self, target_repo: Path) -> tuple[int, list[str]]:
        try:
            diff = subprocess.check_output(
                ["git", "diff", "HEAD"], cwd=target_repo, text=True
            )
            files = subprocess.check_output(
                ["git", "diff", "HEAD", "--name-only"], cwd=target_repo, text=True
            ).splitlines()
            return len(diff.encode("utf-8")), [f for f in files if f]
        except subprocess.CalledProcessError:
            return 0, []

    def invoke(self, prompt: str, target_repo: Path, allowed_tools: list[str],
               timeout_s: int) -> ExecutorResult:
        t0 = time.monotonic()
        binary = self._binary_path()
        if binary is None:
            return ExecutorResult(
                executor=self.name, exit_code=127, duration_ms=0,
                error=("`claude` binary not found on PATH. Install Claude Code "
                       "(npm i -g @anthropic-ai/claude-code) or set CLAUDE_CODE_BIN."),
            )

        # Headless invocation per Claude Code docs (June 2026):
        #   echo <prompt> | claude -p --bare --output-format json
        #          --allowedTools=<csv> --max-turns N
        # The prompt is piped via STDIN, never placed on the command line.
        # Rationale (v1.2.2): passing the prompt as a shell-parsed positional
        # under shell=True on Windows is unsafe — cmd.exe truncates at newlines
        # and treats `||` as a command separator, so the prompt reached `claude`
        # empty. stdin bytes are never shell-parsed, fixing this on all
        # platforms. `--bare` skips hooks/skills/plugins/MCP/auto-memory for
        # reproducible CI runs.
        cmd = [
            binary, "-p", "--bare",
            "--output-format", "json",
            "--max-turns", str(int(os.environ.get("FACTORY_MAX_TURNS", "8"))),
        ]
        if allowed_tools:
            cmd += ["--allowedTools", ",".join(allowed_tools)]

        try:
            proc = cross_platform_run(
                cmd, cwd=str(target_repo),
                input=prompt,  # prompt via stdin — never on the command line
                capture_output=True, text=True, timeout=timeout_s,
                env={**os.environ},  # ANTHROPIC_API_KEY must already be set
            )
            stdout, stderr, code = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as e:
            return ExecutorResult(
                executor=self.name, exit_code=124,
                duration_ms=int((time.monotonic() - t0) * 1000),
                stdout=(e.stdout or b"").decode("utf-8", errors="replace")[-4000:],
                stderr=(e.stderr or b"").decode("utf-8", errors="replace")[-4000:],
                error=f"claude exceeded {timeout_s}s timeout",
            )

        # Parse json output (best-effort; fall back gracefully).
        model_used: str | None = None
        cost_usd = 0.0
        raw: dict = {}
        try:
            parsed = json.loads(stdout)
            raw = parsed if isinstance(parsed, dict) else {"raw": parsed}
            model_used = raw.get("model") or raw.get("model_used")
            cost_usd = float(raw.get("total_cost_usd", raw.get("cost_usd", 0.0)))
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        diff_bytes, files_touched = self._diff_stats(target_repo)

        return ExecutorResult(
            executor=self.name,
            exit_code=code,
            duration_ms=int((time.monotonic() - t0) * 1000),
            stdout=stdout[-4000:],
            stderr=stderr[-4000:],
            diff_size_bytes=diff_bytes,
            files_touched=files_touched,
            model_used=model_used,
            cost_usd=cost_usd,
            raw=raw,
        )
