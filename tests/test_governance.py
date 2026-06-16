import subprocess
from pathlib import Path
from governance import evaluate_action, preflight_target_repo


def test_blocks_destructive_shell():
    d = evaluate_action({"name": "shell", "payload": "sudo rm -rf /"})
    assert d["allowed"] is False
    assert "destructive" in d["reason"]


def test_blocks_production_deploy():
    d = evaluate_action({"name": "production_deploy", "payload": ""})
    assert d["allowed"] is False
    assert d["requires_human_approval"] is True


def test_blocks_hardcoded_secret():
    d = evaluate_action({"name": "implement_change",
                         "payload": "key = 'sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ012345'"})
    assert d["allowed"] is False


def test_blocks_autonomy_overshoot():
    d = evaluate_action({"name": "any", "payload": ""}, autonomy_level=4)
    assert d["allowed"] is False


def test_safe_action_allowed():
    d = evaluate_action({"name": "implement_change", "payload": "edit src/foo.py"})
    assert d["allowed"] is True


# --- v1.1 preflight tests ---

def test_preflight_no_target_allows_mock_only():
    d = preflight_target_repo(None)
    assert d["allowed"] is True


def test_preflight_missing_path_blocks(tmp_path):
    d = preflight_target_repo(tmp_path / "does-not-exist")
    assert d["allowed"] is False
    assert "does not exist" in d["reason"]


def test_preflight_non_git_blocks(tmp_path):
    d = preflight_target_repo(tmp_path)
    assert d["allowed"] is False
    assert "not a git repo" in d["reason"]


def test_preflight_protected_branch_blocks(tmp_path):
    subprocess.check_call(["git", "init", "-b", "main"], cwd=tmp_path,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    d = preflight_target_repo(tmp_path)
    assert d["allowed"] is False
    assert "protected" in d["reason"]


def test_preflight_allows_clean_feature_branch(tmp_path):
    subprocess.check_call(["git", "init", "-b", "feature/work"], cwd=tmp_path,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call(["git", "config", "user.email", "t@t"], cwd=tmp_path)
    subprocess.check_call(["git", "config", "user.name", "t"], cwd=tmp_path)
    (tmp_path / "README.md").write_text("hi")
    subprocess.check_call(["git", "add", "-A"], cwd=tmp_path, stdout=subprocess.DEVNULL)
    subprocess.check_call(["git", "commit", "-m", "init"], cwd=tmp_path,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    d = preflight_target_repo(tmp_path)
    assert d["allowed"] is True
    assert d["branch"] == "feature/work"
    assert d["is_clean"] is True
