"""Governance: autonomy gates, action allow/block, human-approval rules,
target_repo pre-flight (v1.1).

Rules (v1.1):
- Autonomy level >2 requires explicit override (not allowed in v1.1).
- Destructive shell commands are blocked.
- Production deploy requires human approval; v1.1 leaves it fully blocked.
- Hardcoded API key patterns in payloads are blocked.
- Target repo must exist, be a git repo, and (default) be on a non-protected branch.
"""
from __future__ import annotations
import os
import re
import subprocess
from pathlib import Path
from typing import Any
from utils import get_logger, utc_now_iso

log = get_logger("governance")

DESTRUCTIVE_PATTERNS = [
    r"\brm\s+-rf\s+/",
    r"\bmkfs\.",
    r"\bdd\s+if=.+of=/dev/",
    r":\(\)\{:\|:&\};:",  # forkbomb
    r"\bsudo\s+rm\s+-rf",
]
SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9]{20,}",
    r"AKIA[0-9A-Z]{16}",
]
BLOCKED_ACTIONS = {"production_deploy", "delete_production_data", "rotate_secrets_without_approval"}
PROTECTED_BRANCHES = {"main", "master", "production", "release"}


def evaluate_action(action: dict[str, Any], autonomy_level: int = 2) -> dict[str, Any]:
    decision = {
        "timestamp": utc_now_iso(),
        "action": action,
        "autonomy_level": autonomy_level,
        "allowed": True,
        "reason": "default-allow",
        "requires_human_approval": False,
    }
    name = action.get("name", "")
    payload = action.get("payload", "") or ""

    if autonomy_level > 2:
        decision.update(allowed=False, reason=f"autonomy_level {autonomy_level} > max v1 (2)")
    elif name in BLOCKED_ACTIONS:
        decision.update(allowed=False, reason=f"action '{name}' is in BLOCKED_ACTIONS",
                        requires_human_approval=True)
    else:
        for pat in DESTRUCTIVE_PATTERNS:
            if re.search(pat, payload):
                decision.update(allowed=False, reason=f"destructive shell pattern matched: {pat}")
                break
        else:
            for pat in SECRET_PATTERNS:
                if re.search(pat, payload):
                    decision.update(allowed=False, reason=f"hardcoded secret pattern matched: {pat}")
                    break

    log.info("governance: action=%s allowed=%s reason=%s",
             name or "<unnamed>", decision["allowed"], decision["reason"])
    return decision


def requires_human_approval(action_name: str) -> bool:
    return action_name in BLOCKED_ACTIONS


def preflight_target_repo(target_repo: Path | str | None, *,
                          allow_dirty: bool = False,
                          allow_protected_branch: bool = False) -> dict[str, Any]:
    """Validate that a target repo is safe to operate on. v1.1."""
    decision: dict[str, Any] = {
        "timestamp": utc_now_iso(),
        "target_repo": str(target_repo) if target_repo else None,
        "allowed": False,
        "reason": "",
        "branch": None,
        "is_clean": False,
    }
    if target_repo is None:
        decision.update(allowed=True, reason="no target_repo supplied (mock-only run)")
        log.info("preflight: no target_repo (mock-only run allowed)")
        return decision

    p = Path(target_repo).expanduser().resolve()
    if not p.exists():
        decision["reason"] = f"target_repo does not exist: {p}"
        log.info("preflight: %s", decision["reason"])
        return decision
    if not (p / ".git").exists():
        decision["reason"] = f"target_repo is not a git repo (no .git/): {p}"
        log.info("preflight: %s", decision["reason"])
        return decision

    try:
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=p, text=True
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=p, text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        decision["reason"] = f"git query failed: {e}"
        log.info("preflight: %s", decision["reason"])
        return decision

    decision["branch"] = branch
    decision["is_clean"] = (status == "")

    if branch in PROTECTED_BRANCHES and not allow_protected_branch:
        decision["reason"] = f"target_repo on protected branch '{branch}'"
        log.info("preflight: %s", decision["reason"])
        return decision

    if status and not allow_dirty:
        decision["reason"] = "target_repo has uncommitted changes (pass --allow-dirty to override)"
        log.info("preflight: %s", decision["reason"])
        return decision

    decision["allowed"] = True
    decision["reason"] = f"target_repo clean on branch '{branch}'"
    log.info("preflight: target_repo OK branch=%s clean=%s", branch, decision["is_clean"])
    return decision
