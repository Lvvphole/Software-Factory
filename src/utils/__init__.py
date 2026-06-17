"""Shared utilities: structured logging, ID generation, JSON IO."""
from __future__ import annotations
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any


def cross_platform_run(cmd_list: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    """Run a command list reliably across Windows and Unix.

    Windows CreateProcess only executes PE binaries directly; it can't run
    .cmd/.bat shims (npm installs `claude.cmd`), and PATHEXT resolution
    only happens when the shell is involved. Paths containing spaces
    (e.g., `C:\\Users\\Emory Harris\\...`) also need explicit quoting.

    On Windows we route through cmd.exe via shell=True, pre-quoting the
    arg vector with `list2cmdline` so the prompt and args remain
    well-formed even when they contain spaces or quotes. On Unix we keep
    the explicit argv form (safer, no shell interpretation).
    """
    if sys.platform == "win32":
        cmd_str = subprocess.list2cmdline(cmd_list)
        kwargs["shell"] = True
        return subprocess.run(cmd_str, **kwargs)
    return subprocess.run(cmd_list, **kwargs)


def new_run_id() -> str:
    return f"run_{int(time.time())}_{uuid.uuid4().hex[:8]}"


def utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False))
    return path


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logger.addHandler(h)
        logger.setLevel(os.environ.get("FACTORY_LOG_LEVEL", "INFO"))
    return logger
