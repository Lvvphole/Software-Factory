"""Triage: classify signal severity, scope, and routing."""
from __future__ import annotations
from typing import Any
from utils import get_logger, utc_now_iso

log = get_logger("triage")

SEVERITY_SCOPE = {"critical": "large", "high": "medium", "medium": "small", "low": "small"}


def triage(signal: dict[str, Any]) -> dict[str, Any]:
    sev = signal.get("severity", "medium").lower()
    tags = signal.get("tags", [])
    is_security = any(t in tags for t in ("security", "cve", "vulnerability"))
    decision = {
        "triage_id": f"tri_{signal['signal_id']}",
        "signal_id": signal["signal_id"],
        "classified_at": utc_now_iso(),
        "severity": sev,
        "estimated_scope": SEVERITY_SCOPE.get(sev, "small"),
        "is_security_relevant": is_security,
        "requires_human_review": sev == "critical" or is_security,
        "route_to": "planning",
        "rationale": f"severity={sev}, tags={tags}",
    }
    log.info("triage complete: %s scope=%s", decision["triage_id"], decision["estimated_scope"])
    return decision
