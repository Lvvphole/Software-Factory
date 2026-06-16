"""Testing agent (v1 dry-run): emits a test plan + simulated results."""
from __future__ import annotations
from typing import Any
from utils import get_logger, utc_now_iso

log = get_logger("agents.testing")


def run(plan: dict[str, Any], coding_report: dict[str, Any]) -> dict[str, Any]:
    cases = [
        {"id": f"t_{d['step_id']}", "name": f"test for {d['step_id']}",
         "status": "pass" if d.get("status") == "drafted" else "skipped"}
        for d in coding_report.get("diffs", [])
    ]
    passed = sum(1 for c in cases if c["status"] == "pass")
    failed = sum(1 for c in cases if c["status"] == "fail")
    report = {
        "report_id": f"test_{plan['plan_id']}",
        "plan_id": plan["plan_id"],
        "created_at": utc_now_iso(),
        "total": len(cases),
        "passed": passed,
        "failed": failed,
        "skipped": len(cases) - passed - failed,
        "cases": cases,
        "overall": "pass" if failed == 0 else "fail",
    }
    log.info("test report: %s overall=%s", report["report_id"], report["overall"])
    return report
