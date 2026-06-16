"""Security agent (v1): pattern scan on coding_report payloads."""
from __future__ import annotations
import re
from typing import Any
from utils import get_logger, utc_now_iso

log = get_logger("agents.security")

SECRET_PATTERNS = [r"sk-[A-Za-z0-9]{20,}", r"AKIA[0-9A-Z]{16}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"]


def run(plan: dict[str, Any], coding_report: dict[str, Any]) -> dict[str, Any]:
    issues = []
    blob = " ".join(d.get("summary", "") for d in coding_report.get("diffs", []))
    for pat in SECRET_PATTERNS:
        if re.search(pat, blob):
            issues.append({"severity": "critical", "pattern": pat, "message": "secret pattern detected"})
    report = {
        "report_id": f"sec_{plan['plan_id']}",
        "plan_id": plan["plan_id"],
        "created_at": utc_now_iso(),
        "issues": issues,
        "overall": "pass" if not issues else "fail",
    }
    log.info("security report: %s overall=%s issues=%d",
             report["report_id"], report["overall"], len(issues))
    return report
