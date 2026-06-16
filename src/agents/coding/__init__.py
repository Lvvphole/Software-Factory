"""Coding agent (v1 dry-run): produces a structured plan-of-changes report.
Does NOT decide completion (verifier owns that)."""
from __future__ import annotations
from typing import Any
from utils import get_logger, utc_now_iso
from router import route_and_invoke
from governance import evaluate_action

log = get_logger("agents.coding")


def run(plan: dict[str, Any], autonomy_level: int = 2) -> dict[str, Any]:
    diffs = []
    routing_entries = []
    for step in plan.get("steps", []):
        if step.get("agent") != "coding":
            continue
        action = {"name": "implement_change", "payload": f"edit {step.get('target')}"}
        gov = evaluate_action(action, autonomy_level)
        if not gov["allowed"]:
            diffs.append({"step_id": step["id"], "status": "blocked", "reason": gov["reason"]})
            continue
        r = route_and_invoke(f"draft change for step {step['id']}: {step.get('action')}",
                             task_kind="coding")
        routing_entries.append(r)
        diffs.append({
            "step_id": step["id"],
            "status": "drafted",
            "target": step.get("target"),
            "summary": "v1 dry-run: no real file edits; structured intent only",
        })
    report = {
        "report_id": f"code_{plan['plan_id']}",
        "plan_id": plan["plan_id"],
        "created_at": utc_now_iso(),
        "diffs": diffs,
        "routing_entries": routing_entries,
        "self_assessment": "drafted",
        "note": "Coding agent self-assessment is non-authoritative. Verifier decides outcome.",
    }
    log.info("coding report: %s diffs=%d", report["report_id"], len(diffs))
    return report
