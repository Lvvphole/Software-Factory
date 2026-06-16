"""Integration adapters (GitHub, Slack, Jira, etc.) — v1 stubs only."""
from __future__ import annotations
from typing import Any


def emit_external(channel: str, payload: dict[str, Any]) -> dict[str, Any]:
    """v1 stub: returns a record that would be emitted; no network call."""
    return {"channel": channel, "would_emit": True, "payload": payload}
