"""Coding agent (v1.1): delegates to the selected executor.

The agent does NOT decide completion (the verifier does). It collects the
executor result, captures the post-invocation diff from the target repo,
and emits a structured report.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from utils import get_logger, utc_now_iso
from executors import get_executor
from governance import evaluate_action

log = get_logger("agents.coding")

DEFAULT_ALLOWED_TOOLS = ["Read", "Edit", "Write", "Bash(git diff*)", "Bash(git status*)"]


def run(
    plan: dict[str, Any],
    *,
    executor_name: str = "mock",
    target_repo: Path | None = None,
    timeout_s: int = 600,
    autonomy_level: int = 2,
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
            # Mock path or no target_repo (e.g., sample-signal flow).
            res = executor.invoke(
                prompt=f"Implement step {step['id']}: {step.get('action')} on {step.get('target')}",
                target_repo=Path(target_repo) if target_repo else Path("."),
                allowed_tools=DEFAULT_ALLOWED_TOOLS,
                timeout_s=timeout_s,
            )
        else:
            prompt = (
                f"Objective: {plan.get('objective','(unspecified)')}\n"
                f"Step {step['id']}: {step.get('action')} on {step.get('target')}\n"
                f"Make the minimum change required. Run no shell commands beyond git diff/status."
            )
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
        "report_id": f"code_{plan['plan_id']}",
        "plan_id": plan["plan_id"],
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
    log.info("coding report: %s executor=%s diff_bytes=%d files=%d",
             report["report_id"], executor_name, total_diff_bytes, len(files_touched))
    return report
