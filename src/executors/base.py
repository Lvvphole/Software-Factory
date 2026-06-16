"""Executor base — protocol + shared result type.

Executors are the substrate that actually performs work for an agent stage.
v1.1 ships two: mock (no-op) and claude_code (real subprocess to `claude -p`).
Agents talk to executors via a single `invoke()` call; executors return a
mechanical, structured result that the verifier and memory consume.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Protocol


@dataclass
class ExecutorResult:
    executor: str                           # "mock" | "claude_code"
    exit_code: int                          # 0 = ok
    duration_ms: int
    stdout: str = ""                        # truncated tail; full saved separately
    stderr: str = ""
    diff_size_bytes: int = 0                # post-invoke `git diff HEAD` length, bytes
    files_touched: list[str] = field(default_factory=list)
    model_used: str | None = None           # surfaced by executor when available
    cost_usd: float = 0.0
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)  # executor-specific extras

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Executor(Protocol):
    name: str

    def invoke(
        self,
        prompt: str,
        target_repo: Path,
        allowed_tools: list[str],
        timeout_s: int,
    ) -> ExecutorResult: ...
