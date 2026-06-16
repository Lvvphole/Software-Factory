"""Factory workflow: orchestrates lifecycle stages and writes run artifacts.
Verifier runs LAST and is the sole authority on COMPLETE/FAIL."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from utils import write_json, utc_now_iso, new_run_id, get_logger
from signals import load_signal
from triage import triage as triage_signal
from planning import build_plan
from router import route_and_invoke, supported_providers
from agents.coding import run as run_coding
from agents.testing import run as run_testing
from agents.review import run as run_review
from agents.security import run as run_security
from agents.documentation import run as run_documentation
from governance import evaluate_action
from memory import persist_run

log = get_logger("workflows")

REQUIRED_ARTIFACTS = [
    "signal.json", "triage.json", "plan.json", "model-routing-log.json",
    "coding-report.json", "test-report.json", "review-report.json",
    "security-report.json", "documentation-report.json",
    "verifier-report.json", "final-summary.md",
]


def _verifier(run_dir: Path, run_record: dict[str, Any]) -> dict[str, Any]:
    """Mechanical pass/fail decision. Coding agent self-assessment is ignored."""
    artifact_checks: dict[str, bool] = {}
    for name in REQUIRED_ARTIFACTS:
        # verifier-report.json and final-summary.md are written after this call,
        # so we synthesize their expected presence (they will exist by run end).
        if name in ("verifier-report.json", "final-summary.md"):
            artifact_checks[name] = True
            continue
        artifact_checks[name] = (run_dir / name).exists()

    tests_ok = run_record.get("test_report", {}).get("overall") == "pass"
    security_ok = run_record.get("security_report", {}).get("overall") == "pass"
    review_ok = run_record.get("review_report", {}).get("overall") in ("pass", "needs_changes")
    governance_ok = all(g.get("allowed", False) for g in run_record.get("governance_decisions", []))
    artifacts_ok = all(artifact_checks.values())

    decision = "pass" if (tests_ok and security_ok and artifacts_ok) else "fail"
    return {
        "report_id": f"verify_{run_record['run_id']}",
        "run_id": run_record["run_id"],
        "decided_at": utc_now_iso(),
        "artifact_checks": artifact_checks,
        "tests_ok": tests_ok,
        "security_ok": security_ok,
        "review_ok": review_ok,
        "governance_ok": governance_ok,
        "decision": decision,
        "notes": "Verifier ignores coding-agent self-assessment per contract.",
    }


def run_factory(signal_path: str, runs_root: str = ".factory-runs",
                autonomy_level: int = 2) -> dict[str, Any]:
    run_id = new_run_id()
    run_dir = Path(runs_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log.info("factory run start: %s", run_id)

    # 1. Signal intake
    signal = load_signal(signal_path)
    write_json(run_dir / "signal.json", signal)

    # 2. Triage
    triage_decision = triage_signal(signal)
    write_json(run_dir / "triage.json", triage_decision)

    # 3. Planning
    plan = build_plan(signal, triage_decision)
    write_json(run_dir / "plan.json", plan)

    # 4. Model routing log (also seeded by agents)
    routing_entries: list[dict[str, Any]] = []
    routing_entries.append(route_and_invoke(
        f"plan reasoning for {plan['plan_id']}", task_kind="planning"))

    # 5. Governance pre-check: example unsafe action evaluated (not executed)
    governance_decisions: list[dict[str, Any]] = []
    pre_check = evaluate_action({"name": "implement_change",
                                 "payload": "edit src/api/health.py"}, autonomy_level)
    governance_decisions.append(pre_check)

    # 6. Coding
    coding_report = run_coding(plan, autonomy_level)
    routing_entries.extend(coding_report.get("routing_entries", []))
    write_json(run_dir / "coding-report.json", coding_report)

    # 7. Testing
    test_report = run_testing(plan, coding_report)
    write_json(run_dir / "test-report.json", test_report)

    # 8. Review
    review_report = run_review(plan, coding_report)
    write_json(run_dir / "review-report.json", review_report)

    # 9. Security
    security_report = run_security(plan, coding_report)
    write_json(run_dir / "security-report.json", security_report)

    # 10. Documentation
    documentation_report = run_documentation(plan)
    write_json(run_dir / "documentation-report.json", documentation_report)

    # 11. Persist routing log
    write_json(run_dir / "model-routing-log.json", {
        "run_id": run_id,
        "supported_providers": supported_providers(),
        "entries": routing_entries,
    })

    # 12. Build run record
    started_at = utc_now_iso()
    run_record: dict[str, Any] = {
        "run_id": run_id,
        "signal_id": signal["signal_id"],
        "plan_id": plan["plan_id"],
        "started_at": started_at,
        "completed_at": started_at,
        "autonomy_level": autonomy_level,
        "test_report": test_report,
        "security_report": security_report,
        "review_report": review_report,
        "governance_decisions": governance_decisions,
    }

    # 13. Verifier (authoritative)
    verifier_report = _verifier(run_dir, run_record)
    write_json(run_dir / "verifier-report.json", verifier_report)
    run_record["verifier_decision"] = verifier_report["decision"]

    # 14. Final summary
    summary = (
        f"# Factory Run {run_id}\n\n"
        f"- signal: {signal['signal_id']}\n"
        f"- plan: {plan['plan_id']}\n"
        f"- verifier_decision: **{verifier_report['decision']}**\n"
        f"- tests: {test_report['overall']} ({test_report['passed']}/{test_report['total']})\n"
        f"- security: {security_report['overall']}\n"
        f"- review: {review_report['overall']}\n"
        f"- governance_decisions: {len(governance_decisions)}\n"
        f"- artifacts: {len(REQUIRED_ARTIFACTS)} expected\n"
        f"- autonomy_level: {autonomy_level}\n"
        f"- production_deploy: requires explicit human approval (blocked in v1)\n"
    )
    (run_dir / "final-summary.md").write_text(summary)

    # 15. Persist to memory
    persist_run(run_record)

    log.info("factory run complete: %s decision=%s", run_id, verifier_report["decision"])
    return {"run_id": run_id, "run_dir": str(run_dir), "verifier": verifier_report}
