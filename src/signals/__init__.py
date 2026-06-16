"""Signal intake: load external software signals from JSON files."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from utils import read_json, get_logger

log = get_logger("signals")

REQUIRED_FIELDS = ["signal_id", "source", "title", "description"]


def load_signal(path: str | Path) -> dict[str, Any]:
    raw = read_json(Path(path))
    missing = [f for f in REQUIRED_FIELDS if f not in raw]
    if missing:
        raise ValueError(f"signal missing required fields: {missing}")
    log.info("signal loaded: %s from %s", raw["signal_id"], raw.get("source"))
    return raw
