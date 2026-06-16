"""End-to-end v1.1 test: full factory run using a stub claude binary as the
claude_code executor. Validates the capability-grading verifier path.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
import pytest


def _init_demo_target(repo: Path) -> None:
    """Create a minimal demo target with a failing test."""
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


def _make_fix_stub(tmp_path: Path) -> Path:
    """Stub that fixes add() to a + b."""
    stub = tmp_path / "claude_fix.py"
    stub.write_text(textwrap.dedent("""
        #!/usr/bin/env python3
        import json, os, sys
        target = os.path.join(os.getcwd(), "src/calculator/__init__.py")
        with open(target, "w") as f:
            f.write("def add(a, b):\\n    return a + b\\n")
        print(json.dumps({"result":"fixed","session_id":"s","model":"claude-stub","total_cost_usd":0.0}))
    """).strip())
    wrapper = tmp_path / "claude"
    wrapper.write_text(f"#!/usr/bin/env bash\nexec {sys.executable} {stub} \"$@\"\n")
    wrapper.chmod(0o755)
    return wrapper


def test_full_run_with_stub_claude_passes(tmp_path, monkeypatch):
    target_repo = tmp_path / "target"
    _init_demo_target(target_repo)
    stub = _make_fix_stub(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_BIN", str(stub))
    monkeypatch.setenv("FACTORY_DB_PATH", str(tmp_path / "factory.db"))

    # Use a signal file pointing at the demo
    signal_path = tmp_path / "signal.json"
    signal_path.write_text(json.dumps({
        "signal_id": "sig_test_001",
        "source": "test",
        "title": "Fix add()",
        "description": "Replace add() with a + b",
        "severity": "medium",
        "tags": ["bug"],
    }))

    from workflows import run_factory
    result = run_factory(
        str(signal_path),
        runs_root=str(tmp_path / "runs"),
        target_repo=str(target_repo),
        executor="claude_code",
    )
    vr = result["verifier"]
    assert vr["executor"] == "claude_code"
    assert vr["grading_mode"] == "capability"
    assert vr["tests_exit_code"] == 0
    assert vr["diff_size_bytes"] > 0
    assert vr["decision"] == "pass"

    # coding-diff.patch should exist
    assert (Path(result["run_dir"]) / "coding-diff.patch").exists()


def test_full_run_with_stub_that_fails_still_grades_fail(tmp_path, monkeypatch):
    target_repo = tmp_path / "target"
    _init_demo_target(target_repo)
    # Stub that does NOT fix the bug
    stub = tmp_path / "claude_noop.py"
    stub.write_text(textwrap.dedent("""
        #!/usr/bin/env python3
        import json, sys
        # Make a no-op file change that doesn't fix the test
        with open("README_NOTES.md", "w") as f: f.write("notes\\n")
        print(json.dumps({"result":"noop","model":"claude-stub","total_cost_usd":0.0}))
    """).strip())
    wrapper = tmp_path / "claude"
    wrapper.write_text(f"#!/usr/bin/env bash\nexec {sys.executable} {stub} \"$@\"\n")
    wrapper.chmod(0o755)
    monkeypatch.setenv("CLAUDE_CODE_BIN", str(wrapper))
    monkeypatch.setenv("FACTORY_DB_PATH", str(tmp_path / "factory.db"))

    signal_path = tmp_path / "signal.json"
    signal_path.write_text(json.dumps({
        "signal_id": "sig_test_002",
        "source": "test",
        "title": "Fix add()",
        "description": "should fail",
        "severity": "medium",
        "tags": ["bug"],
    }))
    from workflows import run_factory
    result = run_factory(
        str(signal_path),
        runs_root=str(tmp_path / "runs"),
        target_repo=str(target_repo),
        executor="claude_code",
    )
    vr = result["verifier"]
    assert vr["executor"] == "claude_code"
    assert vr["tests_exit_code"] != 0
    assert vr["decision"] == "fail", "verifier must FAIL when real tests fail"
