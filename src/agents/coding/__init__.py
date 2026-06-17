"""Coding agent (v1.2): delegates to the selected executor, accepts an
optional failure_context for retry attempts.

The agent does NOT decide completion (the verifier does). It collects the
executor result, captures the post-invocation diff from the target repo,
and emits a structured report.

v1.2 retry contract: when failure_context is provided, the agent constructs
a structured retry prompt that includes the prior attempt's diff stats and
the test command/output that failed, so the executor can respond to it.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from utils import get_logger, utc_now_iso
from executors import get_executor
from governance import evaluate_action

log = get_logger("agents.coding")

DEFAULT_ALLOWED_TOOLS = ["Read", "Edit", "Write", "Bash(git diff*)", "Bash(git status*)"]


def _truncate(s: str, limit: int = 2000) -> str:
    if not s:
        return ""
    return s if len(s) <= limit else (s[-limit:])


def _build_retry_prompt(plan: dict[str, Any], step: dict[str, Any],
                        failure_context: dict[str, Any]) -> str:
    """Prompt for attempt N (N>=1). Includes prior failure data."""
    attempt_n = failure_context.get("attempt_number", 1)
    prior = failure_context.get("previous_attempts", [])
    last = prior[-1] if prior else {}
    test_cmd = last.get("test_cmd") or []
    test_cmd_s = " ".join(map(str, test_cmd)) if test_cmd else "(unknown)"

    return (
        f"PREVIOUS ATTEMPT FAILED — this is attempt #{attempt_n}.\n"
        f"\n"
        f"Original objective: {plan.get('objective','(unspecified)')}\n"
        f"Step {step['id']}: {step.get('action')} on {step.get('target')}\n"
        f"\n"
        f"Prior attempt produced a diff of {last.get('diff_size_bytes', 0)} bytes "
        f"touching files: {last.get('files_touched', [])}.\n"
        f"\n"
        f"Test command run: {test_cmd_s}\n"
        f"Test exit code: {last.get('test_exit_code', 'unknown')}\n"
        f"\n"
        f"--- Test stdout (tail) ---\n"
        f"{_truncate(last.get('test_stdout_tail', ''))}\n"
        f"--- Test stderr (tail) ---\n"
        f"{_truncate(last.get('test_stderr_tail', ''))}\n"
        f"--- End test output ---\n"
        f"\n"
        f"Diagnose why the previous diff did not make tests pass and fix it.\n"
        f"Make the minimum change required. Run no shell commands beyond git diff/status."
    )


def _build_first_prompt(plan: dict[str, Any], step: dict[str, Any]) -> str:
    return (
        f"Objective: {plan.get('objective','(unspecified)')}\n"
        f"Step {step['id']}: {step.get('action')} on {step.get('target')}\n"
        f"Make the minimum change required. Run no shell commands beyond git diff/status."
    )


def run(
    plan: dict[str, Any],
    *,
    executor_name: str = "mock",
    target_repo: Path | None = None,
    timeout_s: int = 600,
    autonomy_level: int = 2,
    failure_context: dict[str, Any] | None = None,
    attempt_number: int = 0,
) -> dict[str, Any]:
    diffs: list[dict[str, Any]] = []
    executor = get_executor(executor_name)
    total_diff_bytes = 0
    files_touched: list[str] = []
    primary_result_dict: dict[str, Any] | None = None
    model_used: str | None = None
    cost_total = 0.0

    for step in plan.get("steps", []):
        if step.get("agent") != "coding":
            continue
        action = {"name": "implement_change", "payload": f"edit {step.get('target')}"}
        gov = evaluate_action(action, autonomy_level)
        if not gov["allowed"]:
            diffs.append({"step_id": step["id"], "status": "blocked", "reason": gov["reason"]})
            continue

        if executor_name == "mock" or target_repo is None:
            res = executor.invoke(
                prompt=f"Implement step {step['id']}: {step.get('action')} on {step.get('target')}",
                target_repo=Path(target_repo) if target_repo else Path("."),
                allowed_tools=DEFAULT_ALLOWED_TOOLS,
                timeout_s=timeout_s,
            )
        else:
            if failure_context:
                prompt = _build_retry_prompt(plan, step, failure_context)
            else:
                prompt = _build_first_prompt(plan, step)
            res = executor.invoke(
                prompt=prompt,
                target_repo=Path(target_repo),
                allowed_tools=DEFAULT_ALLOWED_TOOLS,
                timeout_s=timeout_s,
            )

        primary_result_dict = res.to_dict()
        total_diff_bytes += res.diff_size_bytes
        for f in res.files_touched:
            if f not in files_touched:
                files_touched.append(f)
        model_used = model_used or res.model_used
        cost_total += res.cost_usd

        diffs.append({
            "step_id": step["id"],
            "status": "executed" if res.exit_code == 0 else "failed",
            "target": step.get("target"),
            "executor": res.executor,
            "exit_code": res.exit_code,
            "diff_size_bytes": res.diff_size_bytes,
            "files_touched": res.files_touched,
            "duration_ms": res.duration_ms,
            "error": res.error,
        })

    report = {
        "report_id": f"code_{plan['plan_id']}_a{attempt_number}",
        "plan_id": plan["plan_id"],
        "attempt_number": attempt_number,
        "is_retry": failure_context is not None,
        "created_at": utc_now_iso(),
        "executor": executor_name,
        "target_repo": str(target_repo) if target_repo else None,
        "diffs": diffs,
        "diff_size_bytes": total_diff_bytes,
        "files_touched": files_touched,
        "model_used": model_used,
        "cost_usd": round(cost_total, 6),
        "primary_executor_result": primary_result_dict,
        "self_assessment": "executed" if total_diff_bytes > 0 or executor_name == "mock" else "no-op",
        "note": "Coding agent self-assessment is non-authoritative. Verifier decides outcome.",
    }
    log.info("coding report: %s attempt=%d executor=%s diff_bytes=%d files=%d",
             report["report_id"], attempt_number, executor_name, total_diff_bytes, len(files_touched))
    return report
