"""Mock executor: no real work, no target_repo writes. Default for CI."""
from __future__ import annotations
import time
from pathlib import Path
from ..base import ExecutorResult


class MockExecutor:
    name = "mock"

    def invoke(self, prompt: str, target_repo: Path, allowed_tools: list[str],
               timeout_s: int) -> ExecutorResult:
        t0 = time.monotonic()
        # Intentionally no target_repo writes. v1.1 verifier knows mock cannot
        # produce a real diff and grades accordingly.
        return ExecutorResult(
            executor="mock",
            exit_code=0,
            duration_ms=int((time.monotonic() - t0) * 1000),
            stdout=f"[mock] would handle: {prompt[:200]}",
            diff_size_bytes=0,
            files_touched=[],
            model_used="mock-v1",
            cost_usd=0.0,
            raw={"allowed_tools": allowed_tools, "target_repo": str(target_repo)},
        )
