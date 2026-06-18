"""Documentation agent (v1.3): real doc-impact analysis over the code diff.

Detects public API surface changes (added/changed top-level def/class, exports)
in the diff and whether documentation was updated in the same change. Drafts
concrete doc targets and flags a gap when public API changed but no docs did.

Deterministic, dependency-free, no LLM call. overall="pass" (advisory): docs
gaps are surfaced as a recommendation, not a hard failure, preserving the v1
verifier contract (documentation is non-blocking).
"""
from __future__ import annotations
import re
from typing import Any
from utils import get_logger, utc_now_iso, parse_unified_diff

log = get_logger("agents.documentation")

_DEF = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_CLASS = re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)")
_EXPORT = re.compile(r"^\s*(?:export\s+(?:default\s+)?(?:function|const|class)\s+([A-Za-z0-9_]+)|module\.exports)")
_DOC_FILE = re.compile(r"(?i)(readme|\.md$|/docs/|changelog|\.rst$)")


def run(plan: dict[str, Any], diff_text: str = "") -> dict[str, Any]:
    parsed = parse_unified_diff(diff_text) if diff_text else {"files": []}

    api_changes: list[dict[str, str]] = []
    docs_touched: list[str] = []
    source_files: list[str] = []

    for f in parsed["files"]:
        path = f.get("path") or ""
        if _DOC_FILE.search(path):
            docs_touched.append(path)
            continue
        if path.endswith((".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java")):
            source_files.append(path)
            for ln in f.get("added_lines", []):
                for pat, kind in ((_DEF, "function"), (_CLASS, "class"), (_EXPORT, "export")):
                    m = pat.search(ln)
                    if m:
                        name = (m.group(1) if m.lastindex else None) or "(anonymous)"
                        # Skip private/dunder helpers for public-API purposes.
                        if name.startswith("_"):
                            continue
                        api_changes.append({"file": path, "kind": kind, "name": name})

    # Plan-declared documentation targets (v1 behavior).
    plan_targets = [s["target"] for s in plan.get("steps", [])
                    if s.get("agent") == "documentation"]

    # Concrete doc targets: plan targets, else README + any touched docs.
    doc_targets = plan_targets or (docs_touched or ["README.md"])

    recommendations: list[str] = []
    api_changed = len(api_changes) > 0
    docs_changed = len(docs_touched) > 0
    if api_changed and not docs_changed:
        names = ", ".join(sorted({c["name"] for c in api_changes})[:8])
        recommendations.append(
            f"Public API changed ({names}) but no documentation was updated. "
            f"Update: {', '.join(doc_targets)}."
        )
    elif api_changed and docs_changed:
        recommendations.append("Public API changed and docs were updated — verify they match.")

    report = {
        "report_id": f"docs_{plan['plan_id']}",
        "plan_id": plan["plan_id"],
        "created_at": utc_now_iso(),
        "doc_targets": doc_targets,
        "api_changes": api_changes,
        "docs_touched": docs_touched,
        "source_files": source_files,
        "documentation_gap": bool(api_changed and not docs_changed),
        "recommendations": recommendations,
        "updates_drafted": True,
        "overall": "pass",
    }
    log.info("documentation report: %s targets=%s api_changes=%d gap=%s",
             report["report_id"], report["doc_targets"],
             len(api_changes), report["documentation_gap"])
    return report
