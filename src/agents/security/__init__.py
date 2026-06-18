"""Security agent (v1.3): real scan over the actual code diff.

Scans ADDED lines of the unified diff for secrets and dangerous constructs.
Deterministic, dependency-free, no LLM call. Security findings are
verifier-BLOCKING: any critical/high issue => overall="fail".

Scanning only added lines (not removed, not context) means removing a secret
doesn't trip the scanner, and unchanged pre-existing lines aren't re-flagged.
"""
from __future__ import annotations
import re
from typing import Any
from utils import get_logger, utc_now_iso, parse_unified_diff

log = get_logger("agents.security")

# (severity, regex, message). Secrets are critical; dangerous calls are high.
_RULES: list[tuple[str, re.Pattern, str]] = [
    ("critical", re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), "Anthropic/OpenAI-style API key"),
    ("critical", re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    ("critical", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
    ("critical", re.compile(r"ghp_[A-Za-z0-9]{30,}"), "GitHub personal access token"),
    ("critical", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"), "Slack token"),
    ("critical", re.compile(r"(?i)\b(password|passwd|secret|api_key|apikey|token)\s*[:=]\s*['\"][^'\"]{6,}['\"]"),
     "hardcoded credential literal"),
    ("high", re.compile(r"\beval\s*\("), "use of eval()"),
    ("high", re.compile(r"\bexec\s*\("), "use of exec()"),
    ("high", re.compile(r"subprocess\.[A-Za-z_]+\([^)]*shell\s*=\s*True"), "subprocess with shell=True"),
    ("high", re.compile(r"\bos\.system\s*\("), "use of os.system()"),
    ("high", re.compile(r"\bpickle\.loads?\s*\("), "pickle deserialization (RCE risk)"),
    ("high", re.compile(r"\byaml\.load\s*\((?![^)]*Loader)"), "yaml.load without SafeLoader"),
    ("medium", re.compile(r"verify\s*=\s*False"), "TLS verification disabled"),
    ("medium", re.compile(r"(?i)#\s*nosec"), "security suppression comment added"),
]

# Lines we never flag for hardcoded-credential (avoid false positives on the
# factory's own placeholders / examples).
_ALLOW = re.compile(r"(?i)(sk-ant-\.\.\.|your[_-]?key|example|placeholder|xxxx|<.*>)")


def run(plan: dict[str, Any], coding_report: dict[str, Any],
        diff_text: str = "") -> dict[str, Any]:
    issues: list[dict[str, Any]] = []

    parsed = parse_unified_diff(diff_text) if diff_text else {"files": []}
    for f in parsed["files"]:
        path = f.get("path") or ""
        for ln in f.get("added_lines", []):
            if _ALLOW.search(ln):
                continue
            for severity, pat, msg in _RULES:
                if pat.search(ln):
                    issues.append({"file": path, "severity": severity,
                                   "message": msg, "line": ln.strip()[:120]})

    # Fallback: also scan any coding_report summaries (v1 behavior retained).
    blob = " ".join(d.get("summary", "") for d in coding_report.get("diffs", []))
    for severity, pat, msg in _RULES:
        if severity == "critical" and pat.search(blob):
            issues.append({"file": "(coding-report summary)", "severity": severity,
                           "message": msg})

    blocking = any(i["severity"] in ("critical", "high") for i in issues)
    overall = "fail" if blocking else "pass"

    report = {
        "report_id": f"sec_{plan['plan_id']}",
        "plan_id": plan["plan_id"],
        "created_at": utc_now_iso(),
        "issues": issues,
        "files_scanned": [f.get("path") for f in parsed["files"]],
        "overall": overall,
    }
    log.info("security report: %s overall=%s issues=%d",
             report["report_id"], report["overall"], len(issues))
    return report
