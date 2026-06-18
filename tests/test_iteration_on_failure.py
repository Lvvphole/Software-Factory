"""v1.2 iteration-on-failure scenarios.

Five tests cover:
  1. first-attempt pass         — stub fixes on first try, no retry.
  2. retry-then-pass            — stub fails on attempt 0, passes on attempt 1.
  3. retry-exhausted-fail       — stub always fails; max_attempts hit; verifier fails.
  4. mock-no-retry              — mock executor must not iterate, regardless of max_attempts.
  5. failure-context-present    — retry prompt contains real failure data; stub writes a sentinel file.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
import pytest
from _stub_claude import make_claude_wrapper
from _iteration_stub import make_retry_aware_stub


# --- shared demo target setup -------------------------------------------------

def _init_demo_target(repo: Path) -> None:
    (repo / "src" / "calculator").mkdir(parents=True)
    (repo / "tests").mkdir(parents=True)
    (repo / "pyproject.toml").write_text(textwrap.dedent("""
        [build-system]
        requires = ["setuptools>=68"]
        build-backend = "setuptools.build_meta"
        [project]
        name = "demo-calculator"
        version = "0.1.0"
        requires-python = ">=3.10"
        [tool.setuptools.packages.find]
        where = ["src"]
    """).strip())
    (repo / "conftest.py").write_text(
        'import sys, os\nsys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))\n'
    )
    (repo / "src" / "calculator" / "__init__.py").write_text(
        "def add(a, b):\n    return a - b  # bug\n"
    )
    (repo / "tests" / "test_calc.py").write_text(
        "from calculator import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
    )
    subprocess.check_call(["git", "init", "-b", "feature/factory"], cwd=repo,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call(["git", "config", "user.email", "t@t"], cwd=repo)
    subprocess.check_call(["git", "config", "user.name", "t"], cwd=repo)
    subprocess.check_call(["git", "add", "-A"], cwd=repo, stdout=subprocess.DEVNULL)
    subprocess.check_call(["git", "commit", "-m", "init"], cwd=repo,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _signal(tmp_path: Path, sig_id: str = "sig_iter_001") -> str:
    p = tmp_path / "signal.json"
    p.write_text(json.dumps({
        "signal_id": sig_id, "source": "test",
        "title": "Fix add()", "description": "Replace add() with a + b",
        "severity": "medium", "tags": ["bug"],
    }))
    return str(p)


# --- 1. first-attempt pass ---------------------------------------------------

def test_first_attempt_pass(tmp_path, monkeypatch):
    target_repo = tmp_path / "target"
    _init_demo_target(target_repo)
    wrapper = make_retry_aware_stub(
        tmp_path,
        first_attempt_action='open(os.path.join(os.getcwd(),"src/calculator/__init__.py"),"w",newline="\\n").write("def add(a, b):\\n    return a + b\\n")',
        retry_action='pass',
    )
    monkeypatch.setenv("CLAUDE_CODE_BIN", str(wrapper))
    monkeypatch.setenv("FACTORY_DB_PATH", str(tmp_path / "f.db"))

    from workflows import run_factory
    result = run_factory(_signal(tmp_path), runs_root=str(tmp_path / "runs"),
                         target_repo=str(target_repo), executor="claude_code",
                         max_attempts=2)
    assert result["verifier"]["decision"] == "pass"
    assert result["attempts_used"] == 1, "should not retry if first attempt passes"

    run_dir = Path(result["run_dir"])
    assert (run_dir / "attempt-0-coding-report.json").exists()
    assert (run_dir / "attempt-0-test-report.json").exists()
    assert not (run_dir / "attempt-1-coding-report.json").exists()
    assert (run_dir / "iteration-report.json").exists()
    iter_rep = json.loads((run_dir / "iteration-report.json").read_text())
    assert iter_rep["attempts_used"] == 1
    assert iter_rep["retry_enabled"] is True
    assert iter_rep["final_overall"] == "pass"


# --- 2. retry-then-pass ------------------------------------------------------

def test_retry_then_pass(tmp_path, monkeypatch):
    target_repo = tmp_path / "target"
    _init_demo_target(target_repo)
    wrapper = make_retry_aware_stub(
        tmp_path,
        # First attempt: write something that still doesn't fix the bug
        first_attempt_action=(
            'open(os.path.join(os.getcwd(),"src/calculator/__init__.py"),"w",newline="\\n")'
            '.write("def add(a, b):\\n    return a * b  # still wrong\\n")'
        ),
        # Retry: write the real fix
        retry_action=(
            'open(os.path.join(os.getcwd(),"src/calculator/__init__.py"),"w",newline="\\n")'
            '.write("def add(a, b):\\n    return a + b\\n")'
        ),
    )
    monkeypatch.setenv("CLAUDE_CODE_BIN", str(wrapper))
    monkeypatch.setenv("FACTORY_DB_PATH", str(tmp_path / "f.db"))

    from workflows import run_factory
    result = run_factory(_signal(tmp_path, "sig_iter_002"),
                         runs_root=str(tmp_path / "runs"),
                         target_repo=str(target_repo), executor="claude_code",
                         max_attempts=2)
    assert result["verifier"]["decision"] == "pass"
    assert result["attempts_used"] == 2

    run_dir = Path(result["run_dir"])
    assert (run_dir / "attempt-0-coding-report.json").exists()
    assert (run_dir / "attempt-0-test-report.json").exists()
    assert (run_dir / "attempt-1-coding-report.json").exists()
    assert (run_dir / "attempt-1-test-report.json").exists()

    # First attempt should have failed; second should have passed.
    a0 = json.loads((run_dir / "attempt-0-test-report.json").read_text())
    a1 = json.loads((run_dir / "attempt-1-test-report.json").read_text())
    assert a0["overall"] == "fail"
    assert a1["overall"] == "pass"

    # attempt-1 coding report should mark itself a retry
    c1 = json.loads((run_dir / "attempt-1-coding-report.json").read_text())
    assert c1["is_retry"] is True
    assert c1["attempt_number"] == 1


# --- 3. retry-exhausted-fail -------------------------------------------------

def test_retry_exhausted_fail(tmp_path, monkeypatch):
    target_repo = tmp_path / "target"
    _init_demo_target(target_repo)
    wrapper = make_retry_aware_stub(
        tmp_path,
        first_attempt_action=(
            'open(os.path.join(os.getcwd(),"src/calculator/__init__.py"),"w",newline="\\n")'
            '.write("def add(a, b):\\n    return a * b  # wrong\\n")'
        ),
        retry_action=(
            'open(os.path.join(os.getcwd(),"src/calculator/__init__.py"),"w",newline="\\n")'
            '.write("def add(a, b):\\n    return a - b - 1  # still wrong\\n")'
        ),
    )
    monkeypatch.setenv("CLAUDE_CODE_BIN", str(wrapper))
    monkeypatch.setenv("FACTORY_DB_PATH", str(tmp_path / "f.db"))

    from workflows import run_factory
    result = run_factory(_signal(tmp_path, "sig_iter_003"),
                         runs_root=str(tmp_path / "runs"),
                         target_repo=str(target_repo), executor="claude_code",
                         max_attempts=2)
    assert result["verifier"]["decision"] == "fail"
    assert result["attempts_used"] == 2

    iter_rep = json.loads((Path(result["run_dir"]) / "iteration-report.json").read_text())
    assert iter_rep["attempts_used"] == iter_rep["max_attempts_effective"]
    assert iter_rep["final_overall"] == "fail"


# --- 4. mock-no-retry --------------------------------------------------------

def test_mock_executor_does_not_iterate(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTORY_DB_PATH", str(tmp_path / "f.db"))

    from workflows import run_factory
    # No target_repo; pure mock path. Even with max_attempts=5 it must NOT iterate.
    result = run_factory("examples/sample-signal.json",
                         runs_root=str(tmp_path / "runs"),
                         executor="mock", max_attempts=5)
    assert result["attempts_used"] == 1, "mock executor must run exactly one attempt"
    iter_rep = json.loads((Path(result["run_dir"]) / "iteration-report.json").read_text())
    assert iter_rep["retry_enabled"] is False
    assert iter_rep["max_attempts_effective"] == 1


# --- 5. failure-context-present ----------------------------------------------

def test_failure_context_present_in_retry(tmp_path, monkeypatch):
    target_repo = tmp_path / "target"
    _init_demo_target(target_repo)

    # On retry the stub writes BOTH the fix AND a sentinel file containing
    # the prompt it received via stdin — proving the failure context was in
    # the prompt that actually reached the executor (v1.2.2: prompt is piped
    # via stdin, not argv).
    wrapper = make_retry_aware_stub(
        tmp_path,
        first_attempt_action=(
            'open(os.path.join(os.getcwd(),"src/calculator/__init__.py"),"w",newline="\\n")'
            '.write("def add(a, b):\\n    return a * b  # wrong\\n")'
        ),
        retry_action=(
            'open(os.path.join(os.getcwd(),"src/calculator/__init__.py"),"w",newline="\\n")'
            '.write("def add(a, b):\\n    return a + b\\n"); '
            'open(os.path.join(os.getcwd(),"PROMPT_RECEIVED.txt"),"w",newline="\\n")'
            '.write(PROMPT_RECEIVED)'
        ),
    )
    monkeypatch.setenv("CLAUDE_CODE_BIN", str(wrapper))
    monkeypatch.setenv("FACTORY_DB_PATH", str(tmp_path / "f.db"))

    from workflows import run_factory
    result = run_factory(_signal(tmp_path, "sig_iter_005"),
                         runs_root=str(tmp_path / "runs"),
                         target_repo=str(target_repo), executor="claude_code",
                         max_attempts=2)
    assert result["verifier"]["decision"] == "pass"
    assert result["attempts_used"] == 2

    sentinel = target_repo / "PROMPT_RECEIVED.txt"
    assert sentinel.exists(), "retry stub did not write its sentinel"
    received = sentinel.read_text()
    # The retry prompt must include the failure marker + test exit code.
    assert "PREVIOUS ATTEMPT FAILED" in received
    assert "Test exit code:" in received
    # And must contain at least part of the prior diff stats.
    assert "Prior attempt produced a diff of" in received
