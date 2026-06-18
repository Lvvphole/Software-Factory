"""Cross-platform stub builder that can branch on retry-vs-first-attempt.

The stub inspects its argv for the "PREVIOUS ATTEMPT FAILED" sentinel that
the v1.2 coding agent injects into retry prompts. On first attempt it runs
the `first` action; on retry it runs `retry`. Both actions are Python
expressions written to a temp file as the stub's body.
"""
from __future__ import annotations
import sys
import textwrap
from pathlib import Path
from _stub_claude import make_claude_wrapper


def make_retry_aware_stub(
    tmp_path: Path,
    first_attempt_action: str,
    retry_action: str,
    name: str = "claude_retry",
) -> Path:
    """Build a stub that performs `first_attempt_action` on attempt 0 and
    `retry_action` on retry attempts.

    Both actions are Python snippets that will execute in cwd=target_repo.
    They have access to the standard library; nothing else is imported.
    """
    stub = tmp_path / f"{name}.py"
    body = textwrap.dedent("""
        import json, os, sys
        # v1.2.2: the prompt now arrives via STDIN (claude -p reads stdin),
        # not as an argv positional. Read it from stdin; fall back to argv
        # for backward compatibility with any caller still passing it inline.
        stdin_blob = ""
        try:
            if not sys.stdin.isatty():
                stdin_blob = sys.stdin.read()
        except Exception:
            stdin_blob = ""
        argv_blob = " ".join(sys.argv)
        prompt_blob = stdin_blob if stdin_blob.strip() else argv_blob
        # Expose for action snippets that want to assert on received prompt.
        PROMPT_RECEIVED = prompt_blob
        is_retry = "PREVIOUS ATTEMPT FAILED" in prompt_blob
        # First / retry action follows.
        if is_retry:
            __RETRY__
        else:
            __FIRST__
        print(json.dumps({
            "result": "retry-fixed" if is_retry else "first-attempt",
            "session_id": "stub-iter",
            "model": "claude-iter-stub",
            "total_cost_usd": 0.0,
        }))
    """).strip()
    body = body.replace("__FIRST__", first_attempt_action.strip() or "pass")
    body = body.replace("__RETRY__", retry_action.strip() or "pass")
    stub.write_text(body)
    return make_claude_wrapper(tmp_path, stub)
