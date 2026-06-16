"""Executor registry. Use get_executor(name) to resolve."""
from __future__ import annotations
from .base import Executor, ExecutorResult
from .mock import MockExecutor
from .claude_code import ClaudeCodeExecutor

_REGISTRY: dict[str, Executor] = {
    "mock": MockExecutor(),
    "claude_code": ClaudeCodeExecutor(),
}


def get_executor(name: str) -> Executor:
    if name not in _REGISTRY:
        raise ValueError(f"unknown executor: {name!r}. choices: {list(_REGISTRY)}")
    return _REGISTRY[name]


def available_executors() -> list[str]:
    return list(_REGISTRY.keys())


__all__ = ["Executor", "ExecutorResult", "get_executor", "available_executors",
           "MockExecutor", "ClaudeCodeExecutor"]
