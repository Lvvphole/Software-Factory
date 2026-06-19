"""Security agent (v1.4): real diff scan + scoped, auditable waivers.

Scans ADDED lines of the unified diff for secrets and dangerous constructs.
Security findings are verifier-BLOCKING: any unwaived critical/high issue
=> overall="fail".

v1.4 adds a WAIVER path. A signal may legitimately need a flagged construct
(e.g. subprocess shell=True in a deploy script). A waiver lets the signal
explicitly authorize a specific finding — auditably:

  signal["security_waivers"] = [
    {"pattern_id": "shell-true",        # which rule (required)
     "file": "scripts/deploy.py",       # optional path scope (substring match)
     "reason": "deploy step needs a shell pipeline",   # required
     "approved_by": "emory"},            # required
    ...
  ]

Waiver semantics (deliberately conservative):
- A waiver only DOWNGRADES a matched finding to status "waived". It never
  hides it: waived findings are recorded separately in the report with the
  reason + approver. Transparency over silent suppression.
- A waiver must name a specific pattern_id. There is NO blanket "waive all".
- reason and approved_by are REQUIRED; a malformed waiver is ignored (the
  finding stays active) and noted in the report.
- Only unwaived critical/high issues block the run.
"""
from __future__ import annotations
import re
from typing import Any
from utils import get_logger, utc_now_iso, parse_unified_diff

log = get_logger("agents.security")

# (pattern_id, severity, regex, message). pattern_id is the stable key a
# waiver references — keep these stable across versions.
_RULES: list[tuple[str, str, re.Pattern, str]] = [
    ("anthropic-openai-key", "critical", re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), "Anthropic/OpenAI-style API key"),
    ("aws-access-key", "critical", re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    ("private-key-block", "critical", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
    ("github-pat", "critical", re.compile(r"ghp_[A-Za-z0-9]{30,}"), "GitHub personal access token"),
    ("slack-token", "critical", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"), "Slack token"),
    ("hardcoded-credential", "critical",
     re.compile(r"(?i)\b(password|passwd|secret|api_key|apikey|token)\s*[:=]\s*['\"][^'\"]{6,}['\"]"),
     "hardcoded credential literal"),
    ("eval", "high", re.compile(r"\beval\s*\("), "use of eval()"),
    ("exec", "high", re.compile(r"\bexec\s*\("), "use of exec()"),
    ("shell-true", "high", re.compile(r"subprocess\.[A-Za-z_]+\([^)]*shell\s*=\s*True"), "subprocess with shell=True"),
    ("os-system", "high", re.compile(r"\bos\.system\s*\("), "use of os.system()"),
    ("pickle-loads", "high", re.compile(r"\bpickle\.loads?\s*\("), "pickle deserialization (RCE risk)"),
    ("yaml-load", "high", re.compile(r"\byaml\.load\s*\((?![^)]*Loader)"), "yaml.load without SafeLoader"),
    ("tls-verify-false", "medium", re.compile(r"verify\s*=\s*False"), "TLS verification disabled"),
    ("nosec-comment", "medium", re.compile(r"(?i)#\s*nosec"), "security suppression comment added"),
]

_ALLOW = re.compile(r"(?i)(sk-ant-\.\.\.|your[_-]?key|example|placeholder|xxxx|<.*>)")


def _valid_waiver(w: Any) -> bool:
    return (
        isinstance(w, dict)
        and isinstance(w.get("pattern_id"), str) and w["pattern_id"].strip()
        and isinstance(w.get("reason"), str) and w["reason"].strip()
        and isinstance(w.get("approved_by"), str) and w["approved_by"].strip()
    )


def _match_waiver(waivers: list[dict[str, Any]], pattern_id: str,
                  file_path: str) -> dict[str, Any] | None:
    """Return the first valid waiver matching this finding, else None.

    A waiver matches when pattern_id is equal AND (no file scope OR the
    finding's path contains the waiver's file substring).
    """
    for w in waivers:
        if not _valid_waiver(w):
            continue
        if w["pattern_id"] != pattern_id:
            continue
        scope = w.get("file")
        if scope and scope not in (file_path or ""):
            continue
        return w
    return None


def run(plan: dict[str, Any], coding_report: dict[str, Any],
        diff_text: str = "", signal: dict[str, Any] | None = None) -> dict[str, Any]:
    signal = signal or {}
    raw_waivers = signal.get("security_waivers") or []
    waivers = [w for w in raw_waivers if isinstance(w, dict)]
    malformed = [w for w in raw_waivers if isinstance(w, dict) and not _valid_waiver(w)]

    issues: list[dict[str, Any]] = []      # active, blocking-eligible
    waived: list[dict[str, Any]] = []      # matched a waiver — recorded, non-blocking

    def _record(file_path: str, pattern_id: str, severity: str, msg: str, line: str):
        w = _match_waiver(waivers, pattern_id, file_path)
        finding = {"file": file_path, "pattern_id": pattern_id,
                   "severity": severity, "message": msg, "line": line}
        if w is not None:
            finding["status"] = "waived"
            finding["waiver_reason"] = w["reason"]
            finding["approved_by"] = w["approved_by"]
            waived.append(finding)
        else:
            finding["status"] = "active"
            issues.append(finding)

    parsed = parse_unified_diff(diff_text) if diff_text else {"files": []}
    for f in parsed["files"]:
        path = f.get("path") or ""
        for ln in f.get("added_lines", []):
            if _ALLOW.search(ln):
                continue
            for pattern_id, severity, pat, msg in _RULES:
                if pat.search(ln):
                    _record(path, pattern_id, severity, msg, ln.strip()[:120])

    # Fallback: scan coding_report summaries for critical patterns (v1 behavior).
    blob = " ".join(d.get("summary", "") for d in coding_report.get("diffs", []))
    for pattern_id, severity, pat, msg in _RULES:
        if severity == "critical" and pat.search(blob):
            _record("(coding-report summary)", pattern_id, severity, msg, "")

    blocking = any(i["severity"] in ("critical", "high") for i in issues)
    overall = "fail" if blocking else "pass"

    report = {
        "report_id": f"sec_{plan['plan_id']}",
        "plan_id": plan["plan_id"],
        "created_at": utc_now_iso(),
        "issues": issues,
        "waived": waived,
        "files_scanned": [f.get("path") for f in parsed["files"]],
        "waivers_applied": len(waived),
        "malformed_waivers": len(malformed),
        "overall": overall,
    }
    log.info("security report: %s overall=%s active=%d waived=%d%s",
             report["report_id"], report["overall"], len(issues), len(waived),
             f" malformed_waivers={len(malformed)}" if malformed else "")
    return report
