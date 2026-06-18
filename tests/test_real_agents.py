"""Tests for the v1.3 real review / security / documentation agents.

Each agent now analyzes the actual unified diff. These tests feed crafted
diffs and assert on the structured findings, preserving the verifier contract:
  - review.overall in {pass, needs_changes}  (non-blocking)
  - security.overall in {pass, fail}          (blocking on critical/high)
  - documentation.overall == pass             (advisory)
"""
from __future__ import annotations
from agents.review import run as run_review
from agents.security import run as run_security
from agents.documentation import run as run_documentation
from utils import parse_unified_diff


PLAN = {"plan_id": "plan_test", "steps": []}
EMPTY_CODING = {"diffs": []}


def _diff(path: str, added: list[str], removed: list[str] | None = None,
          new_file: bool = False) -> str:
    """Build a minimal but valid git unified diff for one file."""
    removed = removed or []
    lines = [f"diff --git a/{path} b/{path}"]
    if new_file:
        lines += ["new file mode 100644", "index 0000000..1111111"]
        lines += ["--- /dev/null", f"+++ b/{path}"]
    else:
        lines += ["index 1111111..2222222 100644", f"--- a/{path}", f"+++ b/{path}"]
    lines.append("@@ -1,1 +1,%d @@" % max(1, len(added)))
    for r in removed:
        lines.append("-" + r)
    for a in added:
        lines.append("+" + a)
    return "\n".join(lines) + "\n"


# ---------- parser ----------

def test_parser_separates_added_and_removed():
    d = _diff("src/x.py", added=["new line one", "new line two"],
              removed=["old line"])
    parsed = parse_unified_diff(d)
    assert len(parsed["files"]) == 1
    f = parsed["files"][0]
    assert f["path"] == "src/x.py"
    assert f["added_lines"] == ["new line one", "new line two"]
    assert f["removed_lines"] == ["old line"]
    assert parsed["added_total"] == 2
    assert parsed["removed_total"] == 1


def test_parser_marks_new_file():
    d = _diff("src/new.py", added=["def f(): pass"], new_file=True)
    parsed = parse_unified_diff(d)
    assert parsed["files"][0]["is_new"] is True


# ---------- review ----------

def test_review_flags_todo_and_print():
    d = _diff("src/app.py", added=["    print('debug')", "    x = 1  # TODO fix"])
    r = run_review(PLAN, EMPTY_CODING, d)
    msgs = " ".join(f["message"] for f in r["findings"])
    assert "debug output" in msgs
    assert "TODO" in msgs
    # print + TODO are medium → still pass (advisory).
    assert r["overall"] == "pass"


def test_review_bare_except_forces_needs_changes():
    d = _diff("src/app.py", added=["    try:", "        go()", "    except:"])
    r = run_review(PLAN, EMPTY_CODING, d)
    assert r["overall"] == "needs_changes"
    assert any(f["severity"] == "high" for f in r["findings"])


def test_review_source_without_tests_is_flagged():
    d = _diff("src/app.py", added=["def feature(): return 1"])
    r = run_review(PLAN, EMPTY_CODING, d)
    assert any("no test files" in f["message"] for f in r["findings"])


def test_review_source_with_tests_no_test_smell():
    d = (_diff("src/app.py", added=["def feature(): return 1"])
         + _diff("tests/test_app.py", added=["def test_feature(): assert feature()==1"]))
    r = run_review(PLAN, EMPTY_CODING, d)
    assert not any("no test files" in f["message"] for f in r["findings"])


def test_review_blocked_step_is_high_finding():
    coding = {"diffs": [{"step_id": "s1", "status": "blocked", "reason": "destructive"}]}
    r = run_review(PLAN, coding, "")
    assert r["overall"] == "needs_changes"
    assert any(f["severity"] == "high" for f in r["findings"])


# ---------- security ----------

def test_security_detects_api_key_in_added_line():
    d = _diff("src/cfg.py", added=['API_KEY = "sk-abcdefghijklmnopqrstuvwxyz123"'])
    r = run_security(PLAN, EMPTY_CODING, d)
    assert r["overall"] == "fail"
    assert any(i["severity"] == "critical" for i in r["issues"])


def test_security_detects_shell_true_and_eval():
    d = _diff("src/run.py", added=[
        "    subprocess.run(cmd, shell=True)",
        "    eval(user_input)",
    ])
    r = run_security(PLAN, EMPTY_CODING, d)
    assert r["overall"] == "fail"
    msgs = " ".join(i["message"] for i in r["issues"])
    assert "shell=True" in msgs
    assert "eval()" in msgs


def test_security_ignores_removed_secret():
    # Secret only on a REMOVED line — must NOT trip the scanner.
    d = _diff("src/cfg.py",
              added=["API_KEY = os.environ['API_KEY']"],
              removed=['API_KEY = "sk-abcdefghijklmnopqrstuvwxyz123"'])
    r = run_security(PLAN, EMPTY_CODING, d)
    assert r["overall"] == "pass"


def test_security_allows_placeholder():
    d = _diff("README.md", added=['export ANTHROPIC_API_KEY="sk-ant-..."'])
    r = run_security(PLAN, EMPTY_CODING, d)
    assert r["overall"] == "pass"


def test_security_clean_diff_passes():
    d = _diff("src/calc.py", added=["def add(a, b):", "    return a + b"])
    r = run_security(PLAN, EMPTY_CODING, d)
    assert r["overall"] == "pass"
    assert r["issues"] == []


# ---------- documentation ----------

def test_docs_flags_api_change_without_docs():
    d = _diff("src/api.py", added=["def public_endpoint(req):", "    return 200"])
    r = run_documentation(PLAN, d)
    assert r["documentation_gap"] is True
    assert any("Public API changed" in rec for rec in r["recommendations"])
    assert r["overall"] == "pass"   # advisory, never blocks


def test_docs_no_gap_when_docs_updated():
    d = (_diff("src/api.py", added=["def public_endpoint(req): return 200"])
         + _diff("README.md", added=["## public_endpoint", "Docs for it."]))
    r = run_documentation(PLAN, d)
    assert r["documentation_gap"] is False
    assert "README.md" in r["docs_touched"]


def test_docs_ignores_private_helpers():
    d = _diff("src/api.py", added=["def _private_helper(): pass"])
    r = run_documentation(PLAN, d)
    assert r["documentation_gap"] is False
    assert r["api_changes"] == []


def test_docs_default_target_is_readme():
    r = run_documentation(PLAN, "")
    assert r["doc_targets"] == ["README.md"]
    assert r["overall"] == "pass"
