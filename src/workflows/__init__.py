"""Factory workflow (v1.1): orchestrates the lifecycle and writes run artifacts.
Verifier runs last and is the sole authority on COMPLETE/FAIL.

v1.1 changes:
  - Accepts target_repo, executor, test_cmd, allow_dirty, allow_protected_branch.
  - Coding agent invokes the selected executor; diff captured to coding-diff.patch.
  - Testing agent runs the real test command in target_repo when present.
  - Verifier grades on capability for real executors:
        pass <=> all_artifacts AND tests_pass AND diff_non_empty
    For mock executor, falls back to artifact-based grading (v1 behavior).
"""
from __future__ import annotations
import json
import subprocess
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
from governance import evaluate_action, preflight_target_repo
from memory import persist_run
from executors import available_executors

log = get_logger("workflows")

REQUIRED_ARTIFACTS = [
    "signal.json", "triage.json", "plan.json", "model-routing-log.json",
    "coding-report.json", "test-report.json", "review-report.json",
    "security-report.json", "documentation-report.json",
    "verifier-report.json", "final-summary.md",
]


def _verifier(run_dir: Path, run_record: dict[str, Any]) -> dict[str, Any]:
    artifact_checks: dict[str, bool] = {}
    for name in REQUIRED_ARTIFACTS:
        if name in ("verifier-report.json", "final-summary.md"):
            artifact_checks[name] = True
            continue
        artifact_checks[name] = (run_dir / name).exists()

    test_report = run_record.get("test_report", {})
    security_ok = run_record.get("security_report", {}).get("overall") == "pass"
    review_ok = run_record.get("review_report", {}).get("overall") in ("pass", "needs_changes")
    governance_ok = all(g.get("allowed", False) for g in run_record.get("governance_decisions", []))
    artifacts_ok = all(artifact_checks.values())

    executor = run_record.get("executor", "mock")
    tests_exit_code = int(test_report.get("exit_code", -1))
    diff_size_bytes = int((run_record.get("coding_report") or {}).get("diff_size_bytes", 0))
    tests_ok = tests_exit_code == 0
    diff_non_empty = diff_size_bytes > 0

    if executor == "mock":
        decision = "pass" if (artifacts_ok and tests_ok and security_ok) else "fail"
        grading_mode = "artifact"
        notes = ("Mock executor — verifier uses v1 artifact + synthetic-test grading. "
                 "Coding-agent self-assessment is ignored per contract.")
    else:
        decision = "pass" if (artifacts_ok and tests_ok and diff_non_empty) else "fail"
        grading_mode = "capability"
        notes = (f"Real executor '{executor}' — verifier grades on tests-pass + "
                 "non-empty diff + artifact set. Coding-agent self-assessment is ignored.")

    return {
        "report_id": f"verify_{run_record['run_id']}",
        "run_id": run_record["run_id"],
        "decided_at": utc_now_iso(),
        "executor": executor,
        "grading_mode": grading_mode,
        "artifact_checks": artifact_checks,
        "tests_exit_code": tests_exit_code,
        "tests_ok": tests_ok,
        "diff_size_bytes": diff_size_bytes,
        "diff_non_empty": diff_non_empty,
        "security_ok": security_ok,
        "review_ok": review_ok,
        "governance_ok": governance_ok,
        "decision": decision,
        "notes": notes,
    }


def run_factory(
    signal_path: str,
    runs_root: str = ".factory-runs",
    autonomy_level: int = 2,
    *,
    target_repo: str | None = None,
    executor: str = "mock",
    test_cmd: list[str] | None = None,
    allow_dirty: bool = False,
    allow_protected_branch: bool = False,
) -> dict[str, Any]:
    if executor not in available_executors():
        raise ValueError(f"unknown executor: {executor!r}; choices: {available_executors()}")

    run_id = new_run_id()
    run_dir = Path(runs_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log.info("factory run start: %s executor=%s target=%s", run_id, executor, target_repo)

    # 1. Signal intake
    signal = load_signal(signal_path)
    write_json(run_dir / "signal.json", signal)

    # 2. Triage
    triage_decision = triage_signal(signal)
    write_json(run_dir / "triage.json", triage_decision)

    # 3. Planning
    plan = build_plan(signal, triage_decision)
    write_json(run_dir / "plan.json", plan)

    # 4. Governance: pre-flight target_repo + sample action
    governance_decisions: list[dict[str, Any]] = []
    preflight = preflight_target_repo(
        target_repo,
        allow_dirty=allow_dirty,
        allow_protected_branch=allow_protected_branch,
    )
    governance_decisions.append({"check": "preflight_target_repo", **preflight})
    pre_check = evaluate_action(
        {"name": "implement_change", "payload": f"edit {target_repo or 'src/...'}"},
        autonomy_level,
    )
    governance_decisions.append({"check": "sample_action", **pre_check})

    # If preflight blocked us and we asked for a non-mock executor, hard-stop coding.
    target_path = Path(target_repo).expanduser().resolve() if (target_repo and preflight["allowed"]) else None

    # 5. Coding
    coding_report = run_coding(
        plan,
        executor_name=executor,
        target_repo=target_path,
        autonomy_level=autonomy_level,
    )
    write_json(run_dir / "coding-report.json", coding_report)

    # 5b. Capture real diff if executor produced one
    if target_path is not None and coding_report.get("diff_size_bytes", 0) > 0:
        try:
            diff_text = subprocess.check_output(
                ["git", "diff", "HEAD"], cwd=target_path, text=True
            )
            (run_dir / "coding-diff.patch").write_text(diff_text)
        except subprocess.CalledProcessError as e:
            log.warning("could not capture coding-diff.patch: %s", e)

    # 6. Testing
    test_report = run_testing(
        plan, coding_report,
        target_repo=target_path,
        test_cmd=test_cmd,
    )
    write_json(run_dir / "test-report.json", test_report)

    # 7. Review (v1 stub, kept)
    review_report = run_review(plan, coding_report)
    write_json(run_dir / "review-report.json", review_report)

    # 8. Security (v1 stub, kept)
    security_report = run_security(plan, coding_report)
    write_json(run_dir / "security-report.json", security_report)

    # 9. Documentation (v1 stub, kept)
    documentation_report = run_documentation(plan)
    write_json(run_dir / "documentation-report.json", documentation_report)

    # 10. Model routing log: surface executor selection as a first-class entry
    routing_entries: list[dict[str, Any]] = []
    routing_entries.append({
        "timestamp": utc_now_iso(),
        "task_kind": "coding",
        "executor": executor,
        "selected_model": coding_report.get("model_used") or executor,
        "selection_reason": f"--executor {executor}",
        "cost_estimate_usd": coding_report.get("cost_usd", 0.0),
        "latency_estimate_ms": (coding_report.get("primary_executor_result") or {}).get("duration_ms", 0),
        "fallback_model": "mock",
        "final_outcome": "ok" if (coding_report.get("primary_executor_result") or {}).get("exit_code", 0) == 0 else "error",
    })
    # Still surface provider router availability for the audit.
    routing_entries.append(route_and_invoke(
        f"plan reasoning for {plan['plan_id']}", task_kind="planning"))
    write_json(run_dir / "model-routing-log.json", {
        "run_id": run_id,
        "supported_providers": supported_providers(),
        "supported_executors": available_executors(),
        "entries": routing_entries,
    })

    # 11. Build run record
    started_at = utc_now_iso()
    run_record: dict[str, Any] = {
        "run_id": run_id,
        "signal_id": signal["signal_id"],
        "plan_id": plan["plan_id"],
        "started_at": started_at,
        "completed_at": started_at,
        "autonomy_level": autonomy_level,
        "executor": executor,
        "target_repo": str(target_path) if target_path else None,
        "coding_report": coding_report,
        "test_report": test_report,
        "security_report": security_report,
        "review_report": review_report,
        "governance_decisions": governance_decisions,
    }

    # 12. Verifier (authoritative)
    verifier_report = _verifier(run_dir, run_record)
    write_json(run_dir / "verifier-report.json", verifier_report)
    run_record["verifier_decision"] = verifier_report["decision"]

    # 13. Final summary
    diff_kb = round(verifier_report["diff_size_bytes"] / 1024.0, 2)
    summary = (
        f"# Factory Run {run_id}\n\n"
        f"- executor: **{executor}** (grading_mode={verifier_report['grading_mode']})\n"
        f"- target_repo: {target_path or '(none — mock-only)'}\n"
        f"- signal: {signal['signal_id']}\n"
        f"- plan: {plan['plan_id']}\n"
        f"- verifier_decision: **{verifier_report['decision']}**\n"
        f"- tests: exit_code={verifier_report['tests_exit_code']} ({test_report.get('overall','n/a')})\n"
        f"- diff_size: {diff_kb} KB across {len(coding_report.get('files_touched', []))} files\n"
        f"- security: {security_report['overall']}\n"
        f"- review: {review_report['overall']}\n"
        f"- governance_decisions: {len(governance_decisions)}\n"
        f"- autonomy_level: {autonomy_level}\n"
        f"- production_deploy: requires explicit human approval (blocked in v1.1)\n"
    )
    (run_dir / "final-summary.md").write_text(summary)

    # 14. Persist to memory
    persist_run(run_record)

    log.info("factory run complete: %s decision=%s", run_id, verifier_report["decision"])
    return {"run_id": run_id, "run_dir": str(run_dir), "verifier": verifier_report}
