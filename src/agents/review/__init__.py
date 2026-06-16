"""Review agent (v1): static review heuristics over coding_report."""
from __future__ import annotations
from typing import Any
from utils import get_logger, utc_now_iso

log = get_logger("agents.review")


def run(plan: dict[str, Any], coding_report: dict[str, Any]) -> dict[str, Any]:
    findings = []
    for d in coding_report.get("diffs", []):
        if d.get("status") == "blocked":
            findings.append({"step_id": d["step_id"], "severity": "high",
                             "message": f"blocked by governance: {d.get('reason')}"})
    report = {
        "report_id": f"review_{plan['plan_id']}",
        "plan_id": plan["plan_id"],
        "created_at": utc_now_iso(),
        "findings": findings,
        "overall": "pass" if not findings else "needs_changes",
    }
    log.info("review report: %s overall=%s findings=%d",
             report["report_id"], report["overall"], len(findings))
    return report
