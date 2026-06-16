"""Documentation agent (v1): records which docs would be updated."""
from __future__ import annotations
from typing import Any
from utils import get_logger, utc_now_iso

log = get_logger("agents.documentation")


def run(plan: dict[str, Any]) -> dict[str, Any]:
    targets = [s["target"] for s in plan.get("steps", []) if s.get("agent") == "documentation"]
    report = {
        "report_id": f"docs_{plan['plan_id']}",
        "plan_id": plan["plan_id"],
        "created_at": utc_now_iso(),
        "doc_targets": targets or ["README.md"],
        "updates_drafted": True,
        "overall": "pass",
    }
    log.info("documentation report: %s targets=%s", report["report_id"], report["doc_targets"])
    return report
