"""Planning: produce a deterministic step plan from a triaged signal."""
from __future__ import annotations
from typing import Any
from utils import get_logger, utc_now_iso

log = get_logger("planning")


def build_plan(signal: dict[str, Any], triage_decision: dict[str, Any]) -> dict[str, Any]:
    steps = [
        {"id": "s1", "agent": "coding", "action": "implement_change", "target": "src/<inferred>"},
        {"id": "s2", "agent": "testing", "action": "add_tests", "target": "tests/<inferred>"},
        {"id": "s3", "agent": "review", "action": "static_review", "target": "diff"},
        {"id": "s4", "agent": "security", "action": "scan_diff", "target": "diff"},
        {"id": "s5", "agent": "documentation", "action": "update_docs", "target": "README.md"},
    ]
    plan = {
        "plan_id": f"plan_{signal['signal_id']}",
        "signal_id": signal["signal_id"],
        "triage_id": triage_decision["triage_id"],
        "created_at": utc_now_iso(),
        "objective": signal["title"],
        "steps": steps,
        "risk_level": "high" if triage_decision["requires_human_review"] else "low",
        "estimated_complexity": triage_decision["estimated_scope"],
        "human_approval_required_for": ["production_deploy"],
    }
    log.info("plan built: %s steps=%d", plan["plan_id"], len(steps))
    return plan
