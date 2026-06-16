from governance import evaluate_action


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
