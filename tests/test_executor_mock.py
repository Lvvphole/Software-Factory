from pathlib import Path
from executors import get_executor, available_executors


def test_registry_has_mock_and_claude_code():
    assert "mock" in available_executors()
    assert "claude_code" in available_executors()


def test_mock_runs_without_target_repo_writes(tmp_path):
    ex = get_executor("mock")
    r = ex.invoke(prompt="hello", target_repo=tmp_path,
                  allowed_tools=["Read"], timeout_s=5)
    assert r.executor == "mock"
    assert r.exit_code == 0
    assert r.diff_size_bytes == 0
    assert r.files_touched == []
    # target_repo unchanged (nothing was even there)
    assert list(tmp_path.iterdir()) == []
