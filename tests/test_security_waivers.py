"""Tests for the v1.4 security waiver path."""
from __future__ import annotations
from agents.security import run as run_security

PLAN = {"plan_id": "plan_w", "steps": []}
EMPTY_CODING = {"diffs": []}


def _diff(path: str, added: list[str]) -> str:
    lines = [f"diff --git a/{path} b/{path}",
             "index 111..222 100644", f"--- a/{path}", f"+++ b/{path}",
             "@@ -1,1 +1,%d @@" % max(1, len(added))]
    lines += ["+" + a for a in added]
    return "\n".join(lines) + "\n"


def _waiver(pattern_id, reason="needed for deploy", approved_by="emory", file=None):
    w = {"pattern_id": pattern_id, "reason": reason, "approved_by": approved_by}
    if file:
        w["file"] = file
    return w


def test_unwaived_shell_true_blocks():
    d = _diff("scripts/deploy.py", ["subprocess.run(cmd, shell=True)"])
    r = run_security(PLAN, EMPTY_CODING, d, {})
    assert r["overall"] == "fail"
    assert r["waivers_applied"] == 0
    assert any(i["pattern_id"] == "shell-true" for i in r["issues"])


def test_waived_shell_true_passes_and_is_recorded():
    d = _diff("scripts/deploy.py", ["subprocess.run(cmd, shell=True)"])
    signal = {"security_waivers": [_waiver("shell-true")]}
    r = run_security(PLAN, EMPTY_CODING, d, signal)
    assert r["overall"] == "pass"            # downgraded, no longer blocks
    assert r["waivers_applied"] == 1
    assert r["issues"] == []                 # nothing active
    assert len(r["waived"]) == 1            # but still recorded
    w = r["waived"][0]
    assert w["pattern_id"] == "shell-true"
    assert w["status"] == "waived"
    assert w["approved_by"] == "emory"
    assert "deploy" in w["waiver_reason"]


def test_waiver_file_scope_must_match():
    d = _diff("src/app.py", ["subprocess.run(cmd, shell=True)"])
    # waiver scoped to scripts/deploy.py — should NOT match src/app.py
    signal = {"security_waivers": [_waiver("shell-true", file="scripts/deploy.py")]}
    r = run_security(PLAN, EMPTY_CODING, d, signal)
    assert r["overall"] == "fail"
    assert r["waivers_applied"] == 0


def test_waiver_file_scope_matches_substring():
    d = _diff("scripts/deploy.py", ["subprocess.run(cmd, shell=True)"])
    signal = {"security_waivers": [_waiver("shell-true", file="deploy.py")]}
    r = run_security(PLAN, EMPTY_CODING, d, signal)
    assert r["overall"] == "pass"
    assert r["waivers_applied"] == 1


def test_waiver_only_covers_named_pattern():
    # eval is waived; an UNwaived hardcoded key in the same diff still blocks.
    d = _diff("src/x.py", [
        "eval(expr)",
        'API_KEY = "sk-abcdefghijklmnopqrstuvwxyz123"',
    ])
    signal = {"security_waivers": [_waiver("eval")]}
    r = run_security(PLAN, EMPTY_CODING, d, signal)
    assert r["overall"] == "fail"            # the key is not waived
    assert r["waivers_applied"] == 1         # eval was waived
    assert any(i["pattern_id"] == "hardcoded-credential" for i in r["issues"])
    assert any(w["pattern_id"] == "eval" for w in r["waived"])


def test_malformed_waiver_ignored_finding_stays_active():
    d = _diff("scripts/deploy.py", ["subprocess.run(cmd, shell=True)"])
    # missing reason + approved_by => malformed => ignored
    signal = {"security_waivers": [{"pattern_id": "shell-true"}]}
    r = run_security(PLAN, EMPTY_CODING, d, signal)
    assert r["overall"] == "fail"
    assert r["waivers_applied"] == 0
    assert r["malformed_waivers"] == 1


def test_no_blanket_waiver():
    # A waiver with a bogus pattern_id does not waive a real finding.
    d = _diff("src/x.py", ["eval(expr)"])
    signal = {"security_waivers": [_waiver("ALL"), _waiver("*")]}
    r = run_security(PLAN, EMPTY_CODING, d, signal)
    assert r["overall"] == "fail"
    assert r["waivers_applied"] == 0


def test_clean_diff_with_waivers_still_passes():
    d = _diff("src/calc.py", ["def add(a, b):", "    return a + b"])
    signal = {"security_waivers": [_waiver("eval")]}
    r = run_security(PLAN, EMPTY_CODING, d, signal)
    assert r["overall"] == "pass"
    assert r["issues"] == []
    assert r["waived"] == []
