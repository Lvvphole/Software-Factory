"""Review agent (v1.3): real static review over the actual code diff.

Reads the unified diff produced by the coding step and applies deterministic,
dependency-free heuristics to the ADDED lines. No LLM call — this runs on every
factory run and must be fast, free, and reproducible (temp-0 philosophy).

Contract preserved from v1:
  overall in {"pass", "needs_changes"}  (verifier treats both as non-blocking;
  "needs_changes" surfaces findings without failing the run).
Governance-blocked steps still produce a high-severity finding.
"""
from __future__ import annotations
import re
from typing import Any
from utils import get_logger, utc_now_iso, parse_unified_diff

log = get_logger("agents.review")

# (severity, regex, message) applied to individual ADDED lines.
_LINE_RULES: list[tuple[str, re.Pattern, str]] = [
    ("medium", re.compile(r"\b(TODO|FIXME|XXX|HACK)\b"),
     "added TODO/FIXME marker left in code"),
    ("medium", re.compile(r"^\s*print\("),
     "added bare print() — likely debug output"),
    ("medium", re.compile(r"^\s*console\.log\("),
     "added console.log — likely debug output"),
    ("high", re.compile(r"^\s*except\s*:\s*$"),
     "bare 'except:' swallows all exceptions"),
    ("medium", re.compile(r"^\s*except\s+Exception\s*:\s*(#.*)?$"),
     "broad 'except Exception:' — narrow if possible"),
    ("low", re.compile(r"\bpdb\.set_trace\(\)|\bbreakpoint\(\)"),
     "debugger breakpoint left in code"),
    ("medium", re.compile(r"^\s*pass\s*#\s*(stub|todo|implement)", re.IGNORECASE),
     "stubbed implementation left as 'pass'"),
]

_LONG_LINE = 120          # chars; flag added lines longer than this
_LARGE_DIFF_LINES = 400   # total added lines over which we warn on size


def run(plan: dict[str, Any], coding_report: dict[str, Any],
        diff_text: str = "") -> dict[str, Any]:
    findings: list[dict[str, Any]] = []

    # Governance-blocked steps remain high-severity findings (v1 behavior).
    for d in coding_report.get("diffs", []):
        if d.get("status") == "blocked":
            findings.append({"step_id": d.get("step_id"), "severity": "high",
                             "message": f"blocked by governance: {d.get('reason')}"})

    parsed = parse_unified_diff(diff_text) if diff_text else {"files": [], "added_total": 0}
    source_changed = False
    tests_changed = False

    for f in parsed["files"]:
        path = f.get("path") or ""
        is_test = "test" in path.lower()
        is_source = path.endswith((".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java"))
        if is_source and not is_test:
            source_changed = True
        if is_test:
            tests_changed = True

        for ln in f.get("added_lines", []):
            for severity, pat, msg in _LINE_RULES:
                if pat.search(ln):
                    findings.append({"file": path, "severity": severity,
                                     "message": msg, "line": ln.strip()[:120]})
            if len(ln) > _LONG_LINE:
                findings.append({"file": path, "severity": "low",
                                 "message": f"added line exceeds {_LONG_LINE} chars",
                                 "line": ln.strip()[:120]})

    # Source changed but no test changes — a real review smell.
    if source_changed and not tests_changed:
        findings.append({"severity": "medium",
                         "message": "source changed but no test files were modified"})

    # Oversized change — worth a human look.
    if parsed.get("added_total", 0) > _LARGE_DIFF_LINES:
        findings.append({"severity": "low",
                         "message": f"large diff: {parsed['added_total']} added lines "
                                    f"(> {_LARGE_DIFF_LINES})"})

    # Any high-severity finding => needs_changes; otherwise pass even with
    # low/medium notes (advisory, non-blocking — preserves v1 verifier contract).
    has_high = any(f["severity"] == "high" for f in findings)
    overall = "needs_changes" if has_high else "pass"

    report = {
        "report_id": f"review_{plan['plan_id']}",
        "plan_id": plan["plan_id"],
        "created_at": utc_now_iso(),
        "findings": findings,
        "files_reviewed": [f.get("path") for f in parsed["files"]],
        "overall": overall,
    }
    log.info("review report: %s overall=%s findings=%d",
             report["report_id"], report["overall"], len(findings))
    return report
