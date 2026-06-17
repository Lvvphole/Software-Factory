"""Testing agent (v1.1): runs a real test command in the target repo when
target_repo is provided, falls back to synthetic results otherwise.

Auto-detection:
  pyproject.toml or setup.py present  -> ["pytest", "-q"]
  package.json present                -> ["npm", "test", "--silent"]
Overridable via test_cmd parameter.
"""
from __future__ import annotations
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from utils import get_logger, utc_now_iso, cross_platform_run

log = get_logger("agents.testing")


def detect_test_cmd(target_repo: Path) -> list[str]:
    if (target_repo / "pyproject.toml").exists() or (target_repo / "setup.py").exists():
        # Use `python -m pytest` rather than bare `pytest` so it works
        # regardless of whether pytest.exe is on PATH (it often isn't on
        # Windows when invoked via shell). sys.executable resolves to the
        # current interpreter on both platforms.
        return [sys.executable, "-m", "pytest", "-q"]
    if (target_repo / "package.json").exists():
        return ["npm", "test", "--silent"]
    return []


def _synthetic(plan: dict[str, Any], coding_report: dict[str, Any]) -> dict[str, Any]:
    cases = [
        {"id": f"t_{d['step_id']}", "name": f"test for {d['step_id']}",
         "status": "pass" if d.get("status") in ("executed", "drafted") else "skipped"}
        for d in coding_report.get("diffs", [])
    ]
    passed = sum(1 for c in cases if c["status"] == "pass")
    failed = sum(1 for c in cases if c["status"] == "fail")
    return {
        "mode": "synthetic",
        "total": len(cases),
        "passed": passed,
        "failed": failed,
        "skipped": len(cases) - passed - failed,
        "cases": cases,
        "exit_code": 0 if failed == 0 else 1,
        "overall": "pass" if failed == 0 else "fail",
    }


def run(
    plan: dict[str, Any],
    coding_report: dict[str, Any],
    *,
    target_repo: Path | None = None,
    test_cmd: list[str] | None = None,
    timeout_s: int = 300,
) -> dict[str, Any]:
    base = {
        "report_id": f"test_{plan['plan_id']}",
        "plan_id": plan["plan_id"],
        "created_at": utc_now_iso(),
    }

    if target_repo is None:
        body = _synthetic(plan, coding_report)
        log.info("test report: %s mode=synthetic overall=%s", base["report_id"], body["overall"])
        return {**base, **body}

    cmd = test_cmd or detect_test_cmd(target_repo)
    if not cmd:
        body = {
            "mode": "real",
            "exit_code": -1,
            "overall": "fail",
            "error": "no test command detected and none supplied",
            "cmd": None,
        }
        log.warning("test report: %s no test command for %s", base["report_id"], target_repo)
        return {**base, **body}

    t0 = time.monotonic()
    try:
        proc = cross_platform_run(cmd, cwd=str(target_repo),
                                  capture_output=True, text=True, timeout=timeout_s)
        stdout, stderr, code = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        stdout = (e.stdout or b"").decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = (e.stderr or b"").decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        body = {
            "mode": "real",
            "cmd": cmd,
            "exit_code": 124,
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "stdout_tail": stdout[-4000:],
            "stderr_tail": stderr[-4000:],
            "overall": "fail",
            "error": f"timeout after {timeout_s}s",
        }
        log.warning("test report: %s timeout", base["report_id"])
        return {**base, **body}

    body = {
        "mode": "real",
        "cmd": cmd,
        "exit_code": code,
        "duration_ms": int((time.monotonic() - t0) * 1000),
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-4000:],
        "overall": "pass" if code == 0 else "fail",
    }
    log.info("test report: %s mode=real exit=%d overall=%s",
             base["report_id"], code, body["overall"])
    return {**base, **body}
