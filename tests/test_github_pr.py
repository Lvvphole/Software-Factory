"""Tests for the v1.3 GitHub PR-creation integration.

No real network calls: the API boundary (_api_request) and git push are
monkeypatched. Tests assert on gating logic, fail-loud behavior, PR body
assembly, and repo-slug parsing.
"""
from __future__ import annotations
import subprocess
from pathlib import Path
import pytest

import integrations.github as gh


# ---------- token / fail-loud ----------

def test_token_missing_raises(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    with pytest.raises(gh.GitHubError) as ei:
        gh._token()
    assert "no GitHub token" in str(ei.value)


def test_token_present_returns(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_dummy")
    assert gh._token() == "ghp_dummy"


# ---------- repo slug parsing ----------

@pytest.mark.parametrize("remote,expected", [
    ("https://github.com/Lvvphole/Software-Factory.git", "Lvvphole/Software-Factory"),
    ("https://github.com/Lvvphole/Software-Factory", "Lvvphole/Software-Factory"),
    ("git@github.com:Lvvphole/Software-Factory.git", "Lvvphole/Software-Factory"),
])
def test_detect_repo_slug(monkeypatch, tmp_path, remote, expected):
    def fake_check_output(cmd, **kw):
        return remote + "\n"
    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    assert gh.detect_repo_slug(tmp_path) == expected


def test_detect_repo_slug_non_github(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "check_output",
                        lambda *a, **k: "https://gitlab.com/x/y.git\n")
    with pytest.raises(gh.GitHubError):
        gh.detect_repo_slug(tmp_path)


# ---------- create_pull_request (mocked API) ----------

def test_create_pull_request_happy_path(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_dummy")
    monkeypatch.setattr(gh, "detect_repo_slug", lambda r: "Lvvphole/Software-Factory")

    captured = {}
    def fake_api(method, url, token, body=None):
        captured["method"] = method
        captured["url"] = url
        captured["body"] = body
        return {"number": 42, "html_url": "https://github.com/Lvvphole/Software-Factory/pull/42",
                "state": "open", "draft": True}
    monkeypatch.setattr(gh, "_api_request", fake_api)

    out = gh.create_pull_request(
        tmp_path, head_branch="feature/factory", base_branch="main",
        title="t", body="b", draft=True)
    assert out["number"] == 42
    assert "pull/42" in out["html_url"]
    assert captured["method"] == "POST"
    assert captured["body"]["draft"] is True
    assert captured["body"]["head"] == "feature/factory"
    assert captured["body"]["base"] == "main"


def test_create_pull_request_no_token_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    with pytest.raises(gh.GitHubError):
        gh.create_pull_request(tmp_path, head_branch="x", base_branch="main",
                               title="t", body="b")


# ---------- PR body assembly ----------

def test_build_pr_body_includes_reports():
    run_record = {
        "run_id": "run_x",
        "signal": {"signal_id": "sig_001", "title": "Fix add()"},
        "attempts_used": 1,
        "verifier": {"decision": "pass", "diff_size_bytes": 260,
                     "tests_ok": True, "security_ok": True, "review_ok": True},
        "review_report": {"overall": "pass", "findings": []},
        "security_report": {"overall": "pass", "issues": []},
        "documentation_report": {"overall": "pass", "documentation_gap": False,
                                 "recommendations": []},
    }
    body = gh.build_pr_body(run_record)
    assert "sig_001" in body
    assert "Fix add()" in body
    assert "Verifier decision" in body
    assert "draft" in body.lower()
    assert "never merges" in body.lower()


# ---------- workflow gating ----------

def _signal_file(tmp_path: Path) -> str:
    p = tmp_path / "sig.json"
    p.write_text('{"signal_id":"sig_pr_001","title":"t","description":"d",'
                 '"severity":"low","source":"manual"}')
    return str(p)


def test_workflow_create_pr_skipped_without_target(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTORY_DB_PATH", str(tmp_path / "f.db"))
    from workflows import run_factory
    result = run_factory(_signal_file(tmp_path),
                         runs_root=str(tmp_path / "runs"),
                         executor="mock", create_pr=True)
    # mock executor => no target_path => PR must be skipped with a reason.
    pr = result["pr_result"]
    assert pr is not None
    assert pr["created"] is False
    assert "no target_repo" in pr["reason"]


def test_workflow_no_pr_when_not_requested(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTORY_DB_PATH", str(tmp_path / "f.db"))
    from workflows import run_factory
    result = run_factory(_signal_file(tmp_path),
                         runs_root=str(tmp_path / "runs"),
                         executor="mock")  # create_pr defaults False
    assert result["pr_result"] is None
