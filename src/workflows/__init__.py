"""Factory workflow (v1.2): orchestrates lifecycle stages, writes run
artifacts, and runs a bounded retry loop on real executors when tests fail.

Verifier runs last and is the sole authority on COMPLETE/FAIL.

v1.2 changes:
  - Retry loop after testing if (executor != mock) AND (target_repo set)
    AND tests fail AND attempt < max_attempts AND governance allows.
  - Each attempt writes attempt-{n}-coding-report.json and
    attempt-{n}-test-report.json into the run dir.
  - Top-level coding-report.json and test-report.json mirror the final
    attempt (backward-compat with v1.1 artifact set).
  - iteration-report.json summarizes attempts, retries, final outcome.
  - Verifier still grades on capability (final tests pass + diff
    non-empty + all artifacts).
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
    "verifier-report.json", "final-summary.md", "iteration-report.json",
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
    attempts_used = int(run_record.get("attempts_used", 1))

    if executor == "mock":
        decision = "pass" if (artifacts_ok and tests_ok and security_ok) else "fail"
        grading_mode = "artifact"
        notes = ("Mock executor — verifier uses v1 artifact + synthetic-test grading. "
                 "Coding-agent self-assessment is ignored per contract.")
    else:
        decision = "pass" if (artifacts_ok and tests_ok and diff_non_empty) else "fail"
        grading_mode = "capability"
        notes = (f"Real executor '{executor}' — verifier grades on tests-pass + "
                 f"non-empty diff + artifact set across {attempts_used} attempt(s). "
                 "Coding-agent self-assessment is ignored.")

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
        "attempts_used": attempts_used,
        "decision": decision,
        "notes": notes,
    }


def _build_failure_context(prior_coding_reports: list[dict[str, Any]],
                           prior_test_reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Compose the structured failure context handed to the coding agent on retry."""
    previous = []
    for cr, tr in zip(prior_coding_reports, prior_test_reports):
        previous.append({
            "attempt": cr.get("attempt_number"),
            "diff_size_bytes": cr.get("diff_size_bytes", 0),
            "files_touched": cr.get("files_touched", []),
            "test_cmd": tr.get("cmd"),
            "test_exit_code": tr.get("exit_code"),
            "test_stdout_tail": tr.get("stdout_tail", ""),
            "test_stderr_tail": tr.get("stderr_tail", ""),
        })
    return {
        "attempt_number": len(previous),  # next attempt's number
        "previous_attempts": previous,
    }


def _git_current_branch(target_repo: Path) -> str:
    """Return the current branch name of the target repo."""
    return subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=target_repo, text=True,
    ).strip()


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
    max_attempts: int = 2,
    create_pr: bool = False,
    pr_base: str = "main",
) -> dict[str, Any]:
    if executor not in available_executors():
        raise ValueError(f"unknown executor: {executor!r}; choices: {available_executors()}")
    if max_attempts < 1:
        raise ValueError(f"max_attempts must be >= 1, got {max_attempts}")

    run_id = new_run_id()
    run_dir = Path(runs_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log.info("factory run start: %s executor=%s target=%s max_attempts=%d",
             run_id, executor, target_repo, max_attempts)

    # 1. Signal intake
    signal = load_signal(signal_path)
    write_json(run_dir / "signal.json", signal)

    # 2. Triage
    triage_decision = triage_signal(signal)
    write_json(run_dir / "triage.json", triage_decision)

    # 3. Planning
    plan = build_plan(signal, triage_decision)
    write_json(run_dir / "plan.json", plan)

    # 4. Governance pre-flight
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
    target_path = Path(target_repo).expanduser().resolve() if (target_repo and preflight["allowed"]) else None

    # Retry loop is only valid for real executors with a target repo.
    retry_enabled = (executor != "mock") and (target_path is not None)
    effective_max_attempts = max_attempts if retry_enabled else 1

    coding_reports: list[dict[str, Any]] = []
    test_reports: list[dict[str, Any]] = []
    attempt_records: list[dict[str, Any]] = []

    for attempt in range(effective_max_attempts):
        failure_context = None
        if attempt > 0:
            failure_context = _build_failure_context(coding_reports, test_reports)

        # Coding
        coding_report = run_coding(
            plan,
            executor_name=executor,
            target_repo=target_path,
            autonomy_level=autonomy_level,
            failure_context=failure_context,
            attempt_number=attempt,
        )
        write_json(run_dir / f"attempt-{attempt}-coding-report.json", coding_report)
        coding_reports.append(coding_report)

        # Testing
        test_report = run_testing(
            plan, coding_report,
            target_repo=target_path,
            test_cmd=test_cmd,
        )
        # Inject attempt number so attempt records line up.
        test_report["attempt_number"] = attempt
        write_json(run_dir / f"attempt-{attempt}-test-report.json", test_report)
        test_reports.append(test_report)

        attempt_records.append({
            "attempt_number": attempt,
            "is_retry": attempt > 0,
            "diff_size_bytes": coding_report.get("diff_size_bytes", 0),
            "files_touched": coding_report.get("files_touched", []),
            "test_exit_code": int(test_report.get("exit_code", -1)),
            "test_overall": test_report.get("overall"),
        })

        # Decide: continue, stop with pass, or stop with attempts exhausted.
        tests_passed = int(test_report.get("exit_code", -1)) == 0
        if tests_passed:
            log.info("factory run %s: attempt %d tests pass — stopping retry loop", run_id, attempt)
            break
        if attempt + 1 >= effective_max_attempts:
            log.info("factory run %s: attempt %d failed, attempts exhausted", run_id, attempt)
            break
        # Governance check for retry — same rules, but logged separately.
        retry_gov = evaluate_action(
            {"name": "implement_change_retry", "payload": f"retry edit on {target_path}"},
            autonomy_level,
        )
        governance_decisions.append({"check": f"retry_attempt_{attempt+1}", **retry_gov})
        if not retry_gov["allowed"]:
            log.info("factory run %s: retry blocked by governance — stopping", run_id)
            break
        log.info("factory run %s: attempt %d failed, retrying (attempt %d)",
                 run_id, attempt, attempt + 1)

    final_coding = coding_reports[-1]
    final_test = test_reports[-1]
    attempts_used = len(coding_reports)

    # Mirror final attempt to backward-compatible names.
    write_json(run_dir / "coding-report.json", final_coding)
    write_json(run_dir / "test-report.json", final_test)

    # Capture real diff from target repo if executor produced one.
    diff_text = ""
    if target_path is not None and final_coding.get("diff_size_bytes", 0) > 0:
        try:
            diff_text = subprocess.check_output(
                ["git", "diff", "HEAD"], cwd=target_path, text=True
            )
            (run_dir / "coding-diff.patch").write_text(diff_text)
        except subprocess.CalledProcessError as e:
            log.warning("could not capture coding-diff.patch: %s", e)

    # Review / Security / Documentation: real analysis over the actual diff.
    review_report = run_review(plan, final_coding, diff_text)
    write_json(run_dir / "review-report.json", review_report)

    security_report = run_security(plan, final_coding, diff_text)
    write_json(run_dir / "security-report.json", security_report)

    documentation_report = run_documentation(plan, diff_text)
    write_json(run_dir / "documentation-report.json", documentation_report)

    # Iteration report (new in v1.2)
    iteration_report = {
        "report_id": f"iter_{run_id}",
        "run_id": run_id,
        "executor": executor,
        "max_attempts_configured": max_attempts,
        "max_attempts_effective": effective_max_attempts,
        "attempts_used": attempts_used,
        "retry_enabled": retry_enabled,
        "attempts": attempt_records,
        "final_test_exit_code": int(final_test.get("exit_code", -1)),
        "final_overall": final_test.get("overall"),
        "note": "Verifier grades on the final attempt's outcome.",
    }
    write_json(run_dir / "iteration-report.json", iteration_report)

    # Model routing log
    routing_entries: list[dict[str, Any]] = []
    routing_entries.append({
        "timestamp": utc_now_iso(),
        "task_kind": "coding",
        "executor": executor,
        "selected_model": final_coding.get("model_used") or executor,
        "selection_reason": f"--executor {executor}",
        "cost_estimate_usd": sum(c.get("cost_usd", 0.0) for c in coding_reports),
        "latency_estimate_ms": sum(
            (c.get("primary_executor_result") or {}).get("duration_ms", 0)
            for c in coding_reports
        ),
        "fallback_model": "mock",
        "final_outcome": "ok" if int(final_test.get("exit_code", -1)) == 0 else "error",
        "attempts_used": attempts_used,
    })
    routing_entries.append(route_and_invoke(
        f"plan reasoning for {plan['plan_id']}", task_kind="planning"))
    write_json(run_dir / "model-routing-log.json", {
        "run_id": run_id,
        "supported_providers": supported_providers(),
        "supported_executors": available_executors(),
        "entries": routing_entries,
    })

    # Build run record
    started_at = utc_now_iso()
    run_record: dict[str, Any] = {
        "run_id": run_id,
        "signal_id": signal["signal_id"],
        "signal": signal,
        "plan_id": plan["plan_id"],
        "started_at": started_at,
        "completed_at": started_at,
        "autonomy_level": autonomy_level,
        "executor": executor,
        "target_repo": str(target_path) if target_path else None,
        "coding_report": final_coding,
        "test_report": final_test,
        "security_report": security_report,
        "review_report": review_report,
        "documentation_report": documentation_report,
        "governance_decisions": governance_decisions,
        "attempts_used": attempts_used,
        "iteration_report": iteration_report,
    }

    # Verifier
    verifier_report = _verifier(run_dir, run_record)
    write_json(run_dir / "verifier-report.json", verifier_report)
    run_record["verifier_decision"] = verifier_report["decision"]

    # ---- Optional: real PR creation (v1.3) -------------------------------
    # Side-effectful REMOTE WRITE. Gated by ALL of:
    #   1. opt-in (create_pr=True)
    #   2. a real target repo exists
    #   3. verifier decision == "pass" (never PR a failed run)
    #   4. governance allows the 'create_pull_request' action
    # The factory opens a DRAFT PR and never merges. Token comes from env only.
    pr_result: dict[str, Any] | None = None
    if create_pr:
        if target_path is None:
            pr_result = {"created": False, "reason": "no target_repo — cannot create PR"}
            log.warning("create_pr requested but no target_repo; skipping")
        elif verifier_report["decision"] != "pass":
            pr_result = {"created": False,
                         "reason": f"verifier decision is '{verifier_report['decision']}', not 'pass'"}
            log.warning("create_pr requested but verifier did not pass; skipping")
        else:
            gov = evaluate_action(
                {"name": "create_pull_request",
                 "payload": f"open draft PR for {signal['signal_id']} on {target_path}"},
                autonomy_level,
            )
            governance_decisions.append({"check": "create_pull_request", **gov})
            if not gov["allowed"]:
                pr_result = {"created": False,
                             "reason": f"governance blocked PR creation: {gov['reason']}"}
                log.warning("governance blocked PR creation: %s", gov["reason"])
            else:
                from integrations.github import (
                    GitHubError, build_pr_body, create_pull_request, push_branch,
                )
                try:
                    head_branch = _git_current_branch(target_path)
                    push_branch(target_path, head_branch)
                    body = build_pr_body(run_record)
                    title = f"[factory] {signal.get('title') or signal['signal_id']}"
                    pr = create_pull_request(
                        target_path,
                        head_branch=head_branch,
                        base_branch=pr_base,
                        title=title,
                        body=body,
                        draft=True,
                    )
                    pr_result = {"created": True, **pr}
                except GitHubError as e:
                    # Fail loudly in the artifact; do NOT crash the whole run
                    # (the code change + verifier verdict are still valid).
                    pr_result = {"created": False, "reason": str(e)}
                    log.error("PR creation failed: %s", e)

        run_record["pr_result"] = pr_result
        write_json(run_dir / "pr-result.json", pr_result)

    # Final summary
    diff_kb = round(verifier_report["diff_size_bytes"] / 1024.0, 2)
    retry_status = (
        f"{attempts_used}/{effective_max_attempts} attempts used"
        + ("" if effective_max_attempts == 1 else f" (max_attempts={max_attempts})")
    )
    summary = (
        f"# Factory Run {run_id}\n\n"
        f"- executor: **{executor}** (grading_mode={verifier_report['grading_mode']})\n"
        f"- target_repo: {target_path or '(none — mock-only)'}\n"
        f"- signal: {signal['signal_id']}\n"
        f"- plan: {plan['plan_id']}\n"
        f"- iteration: {retry_status}\n"
        f"- verifier_decision: **{verifier_report['decision']}**\n"
        f"- final tests: exit_code={verifier_report['tests_exit_code']} ({final_test.get('overall','n/a')})\n"
        f"- final diff_size: {diff_kb} KB across {len(final_coding.get('files_touched', []))} files\n"
        f"- security: {security_report['overall']}\n"
        f"- review: {review_report['overall']}\n"
        f"- governance_decisions: {len(governance_decisions)}\n"
        f"- autonomy_level: {autonomy_level}\n"
        f"- production_deploy: requires explicit human approval (blocked in v1.2)\n"
    )
    (run_dir / "final-summary.md").write_text(summary)

    persist_run(run_record)

    log.info("factory run complete: %s attempts=%d decision=%s",
             run_id, attempts_used, verifier_report["decision"])
    return {"run_id": run_id, "run_dir": str(run_dir), "verifier": verifier_report,
            "attempts_used": attempts_used, "iteration_report": iteration_report,
            "pr_result": pr_result}
