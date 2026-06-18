"""Tests for ClaudeCodeExecutor using a stub `claude` binary.

The stub mimics `claude --print --bare ...` by making a deterministic file edit
in cwd (the target_repo) and emitting valid JSON on stdout. No real API call.
Cross-platform via tests/_stub_claude.py.
"""
from __future__ import annotations
import os
import subprocess
import sys
import textwrap
from pathlib import Path
import pytest
from executors import get_executor
from _stub_claude import make_claude_wrapper


def _make_fix_stub(tmp_path: Path,
                   edit_file: str = "src/calculator/__init__.py",
                   new_content: str = '"""Stubbed."""\n\ndef add(a, b):\n    return a + b\n\ndef mul(a, b):\n    return a * b\n') -> Path:
    stub = tmp_path / "claude_stub.py"
    stub.write_text(textwrap.dedent(f"""
        #!/usr/bin/env python3
        import json, os, sys
        target = os.path.join(os.getcwd(), {edit_file!r})
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", newline="\\n") as f:
            f.write({new_content!r})
        out = {{
            "result": "fixed add() to return a + b",
            "session_id": "stub-session",
            "model": "claude-stub",
            "total_cost_usd": 0.0,
            "num_turns": 1,
        }}
        print(json.dumps(out))
        sys.exit(0)
    """).strip())
    return make_claude_wrapper(tmp_path, stub)


def _make_failing_stub(tmp_path: Path) -> Path:
    stub = tmp_path / "claude_fail.py"
    stub.write_text(textwrap.dedent("""
        #!/usr/bin/env python3
        import sys
        print("simulated error", file=sys.stderr)
        sys.exit(2)
    """).strip())
    return make_claude_wrapper(tmp_path, stub)


def _init_target_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "src" / "calculator").mkdir(parents=True)
    (repo / "src" / "calculator" / "__init__.py").write_text(
        "def add(a, b):\n    return a - b  # bug\n"
    )
    subprocess.check_call(["git", "init", "-b", "feature/factory"], cwd=repo,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call(["git", "config", "user.email", "t@t"], cwd=repo)
    subprocess.check_call(["git", "config", "user.name", "t"], cwd=repo)
    subprocess.check_call(["git", "add", "-A"], cwd=repo, stdout=subprocess.DEVNULL)
    subprocess.check_call(["git", "commit", "-m", "init"], cwd=repo,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def test_missing_binary_returns_127(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_BIN", raising=False)
    monkeypatch.setenv("PATH", "/nonexistent" if sys.platform != "win32" else "C:\\nonexistent")
    ex = get_executor("claude_code")
    r = ex.invoke(prompt="x", target_repo=tmp_path,
                  allowed_tools=["Read"], timeout_s=5)
    assert r.exit_code == 127
    assert r.error and "claude" in r.error.lower()


def test_stub_invocation_produces_real_diff(tmp_path, monkeypatch):
    repo = tmp_path / "target"
    _init_target_repo(repo)
    wrapper = _make_fix_stub(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_BIN", str(wrapper))

    ex = get_executor("claude_code")
    r = ex.invoke(
        prompt="Fix add()",
        target_repo=repo,
        allowed_tools=["Read", "Edit", "Write"],
        timeout_s=15,
    )
    assert r.executor == "claude_code"
    assert r.exit_code == 0, f"executor failed: stderr={r.stderr!r} error={r.error!r}"
    assert r.diff_size_bytes > 0, "expected a real git diff after stub edit"
    assert "src/calculator/__init__.py" in r.files_touched
    assert r.model_used == "claude-stub"


def test_stub_failure_propagates_exit_code(tmp_path, monkeypatch):
    repo = tmp_path / "target"
    _init_target_repo(repo)
    wrapper = _make_failing_stub(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_BIN", str(wrapper))

    ex = get_executor("claude_code")
    r = ex.invoke(prompt="anything", target_repo=repo,
                  allowed_tools=[], timeout_s=5)
    assert r.exit_code == 2
    assert r.diff_size_bytes == 0


def _make_stdin_echo_stub(tmp_path: Path) -> Path:
    """Stub that proves the prompt arrived via STDIN, intact and multi-line.

    It reads the full prompt from stdin and writes it verbatim to
    PROMPT_VIA_STDIN.txt in cwd. This is the regression guard for the
    v1.2.2 fix: prior to it, a multi-line prompt passed as a shell-parsed
    argv positional under shell=True on Windows reached `claude` empty
    (Error: Input must be provided ... when using --print).
    """
    stub = tmp_path / "claude_echo.py"
    stub.write_text(textwrap.dedent("""
        #!/usr/bin/env python3
        import json, os, sys
        data = sys.stdin.read()
        with open(os.path.join(os.getcwd(), "PROMPT_VIA_STDIN.txt"),
                  "w", newline="\\n") as f:
            f.write(data)
        # Also make a real edit so the diff is non-empty.
        t = os.path.join(os.getcwd(), "src", "calculator", "__init__.py")
        os.makedirs(os.path.dirname(t), exist_ok=True)
        with open(t, "w", newline="\\n") as f:
            f.write("def add(a, b):\\n    return a + b\\n")
        print(json.dumps({"result": "ok", "session_id": "echo",
                          "model": "claude-echo", "total_cost_usd": 0.0}))
        sys.exit(0)
    """).strip())
    return make_claude_wrapper(tmp_path, stub)


def test_multiline_prompt_reaches_executor_via_stdin(tmp_path, monkeypatch):
    repo = tmp_path / "target"
    _init_target_repo(repo)
    wrapper = _make_stdin_echo_stub(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_BIN", str(wrapper))

    multiline = (
        "Objective: Fix add()\n"
        "PREVIOUS ATTEMPT FAILED — this is attempt #1.\n"
        "Test exit code: 1\n"
        "Prior attempt produced a diff of 249 bytes\n"
        "Lines with || pipes and \"quotes\" and spaces must survive."
    )
    ex = get_executor("claude_code")
    r = ex.invoke(prompt=multiline, target_repo=repo,
                  allowed_tools=["Read", "Edit"], timeout_s=10)
    assert r.exit_code == 0

    received = (repo / "PROMPT_VIA_STDIN.txt").read_text()
    # The ENTIRE multi-line prompt must arrive — not just the first line.
    assert "Objective: Fix add()" in received
    assert "PREVIOUS ATTEMPT FAILED" in received
    assert "Test exit code: 1" in received
    assert "Prior attempt produced a diff of 249 bytes" in received
    assert "|| pipes" in received          # the char that broke v1.2.1
    assert '"quotes"' in received
