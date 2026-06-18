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


def sanitize_prompt_for_shell(prompt: str) -> str:
    """DEPRECATED / identity. Retained for backward compatibility.

    History:
      - v1.2.1 replaced newlines with `` || `` to survive cmd.exe argv
        truncation when the prompt was passed as a shell-parsed positional
        under ``shell=True``.
      - That fix was unsafe: `` || `` is the cmd.exe command separator, so a
        prompt routed through ``list2cmdline`` + ``shell=True`` got split into
        multiple shell commands, and the prompt positional reached ``claude``
        empty (``Error: Input must be provided ... when using --print``).

    v1.2.2 removes the root cause: the prompt is no longer passed on the
    command line at all. It is piped to the child process via **stdin**
    (``claude -p`` reads the prompt from stdin), where bytes are never parsed
    by any shell. Newlines, ``||``, quotes, spaces and arg-length limits all
    become non-issues on every platform.

    This function is now an identity transform. Callers should pass the prompt
    via stdin (see ``cross_platform_run(..., input=...)``). Kept so existing
    imports/tests don't break.
    """
    return prompt


def new_run_id() -> str:
    return f"run_{int(time.time())}_{uuid.uuid4().hex[:8]}"


def utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False))
    return path


def parse_unified_diff(diff_text: str) -> dict[str, Any]:
    """Parse a `git diff` unified patch into a structured form.

    Returns:
      {
        "files": [
          {"path": "<new path>", "old_path": "<old path>",
           "added_lines": [str, ...],     # content of '+' lines (no prefix)
           "removed_lines": [str, ...],   # content of '-' lines (no prefix)
           "is_new": bool, "is_deleted": bool}
        ],
        "added_total": int,
        "removed_total": int,
      }

    Deterministic, dependency-free. Only the line CONTENT is captured (the
    leading +/- is stripped) so agents can scan exactly what was introduced.
    Diff metadata lines (+++/---) are excluded from added/removed content.
    """
    files: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    added_total = 0
    removed_total = 0

    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            if cur is not None:
                files.append(cur)
            cur = {"path": None, "old_path": None, "added_lines": [],
                   "removed_lines": [], "is_new": False, "is_deleted": False}
            continue
        if cur is None:
            continue
        if line.startswith("new file mode"):
            cur["is_new"] = True
        elif line.startswith("deleted file mode"):
            cur["is_deleted"] = True
        elif line.startswith("--- "):
            p = line[4:].strip()
            cur["old_path"] = None if p == "/dev/null" else p[2:] if p.startswith("a/") else p
        elif line.startswith("+++ "):
            p = line[4:].strip()
            cur["path"] = None if p == "/dev/null" else p[2:] if p.startswith("b/") else p
        elif line.startswith("+") and not line.startswith("+++"):
            cur["added_lines"].append(line[1:])
            added_total += 1
        elif line.startswith("-") and not line.startswith("---"):
            cur["removed_lines"].append(line[1:])
            removed_total += 1

    if cur is not None:
        files.append(cur)

    # Fall back path name to old_path when needed (renames/deletes).
    for f in files:
        if not f["path"]:
            f["path"] = f["old_path"]

    return {"files": files, "added_total": added_total,
            "removed_total": removed_total}


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
