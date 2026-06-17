"""Cross-platform `claude` stub helpers for tests.

On Linux we create a bash wrapper with chmod +x.
On Windows we create a `claude.cmd` that invokes the Python stub via cmd.exe.
Either way, callers set `CLAUDE_CODE_BIN` to the returned path. The production
executor uses utils.cross_platform_run() which handles cmd.exe shimming +
path-with-spaces quoting via list2cmdline.
"""
from __future__ import annotations
import sys
from pathlib import Path


def make_claude_wrapper(tmp_path: Path, stub_py_path: Path) -> Path:
    if sys.platform == "win32":
        wrapper = tmp_path / "claude.cmd"
        wrapper.write_text(
            f'@echo off\r\n"{sys.executable}" "{stub_py_path}" %*\r\n'
        )
    else:
        wrapper = tmp_path / "claude"
        wrapper.write_text(
            f"#!/usr/bin/env bash\nexec {sys.executable} {stub_py_path} \"$@\"\n"
        )
        wrapper.chmod(0o755)
    return wrapper
