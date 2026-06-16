"""Governance: autonomy gates, action allow/block, human-approval rules.

Rules (v1):
- Autonomy level >2 requires explicit override (not allowed in v1 dry-run).
- Destructive shell commands are blocked.
- Production deploy requires human approval; in v1 it is fully blocked at execution time.
- Hardcoded API key patterns in code outputs are blocked.
"""
from __future__ import annotations
import os
import re
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


def evaluate_action(action: dict[str, Any], autonomy_level: int = 2) -> dict[str, Any]:
    """Return decision: {allowed: bool, reason, timestamp, action}."""
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
