"""GitHub integration (v1.3): real Pull Request creation.

Stdlib-only (urllib) — no new dependencies. Talks to the GitHub REST API.

Design constraints (consistent with the factory's governance model):
- This is a side-effectful REMOTE WRITE. It is OPT-IN (caller must request it)
  and never runs by default.
- Credentials come ONLY from the environment (GITHUB_TOKEN). Never logged,
  never written to artifacts, never committed.
- Fails LOUDLY: if asked to create a PR without a token or required inputs,
  raises GitHubError rather than silently no-op'ing.
- The caller (workflow) is responsible for gating on verifier=pass and
  governance approval BEFORE calling create_pull_request().
"""
from __future__ import annotations
import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from utils import get_logger

log = get_logger("integrations.github")

_API = "https://api.github.com"


class GitHubError(RuntimeError):
    """Raised for any GitHub integration failure (auth, network, API)."""


def _token() -> str:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not tok:
        raise GitHubError(
            "PR creation requested but no GitHub token found. "
            "Set GITHUB_TOKEN (a fine-grained PAT with 'Contents' + "
            "'Pull requests' write on the target repo) in the environment. "
            "The factory never reads tokens from files or arguments."
        )
    return tok


def _api_request(method: str, url: str, token: str,
                 body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "software-factory")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        # Never echo the token; only the server's message.
        raise GitHubError(f"GitHub API {method} {url.split(_API)[-1]} "
                          f"failed: HTTP {e.code} {detail}") from None
    except urllib.error.URLError as e:
        raise GitHubError(f"GitHub API network error: {e.reason}") from None


def detect_repo_slug(target_repo: Path) -> str:
    """Return 'owner/name' from the target repo's 'origin' remote.

    Supports https and ssh remote URLs. Raises GitHubError if it can't.
    """
    try:
        url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=target_repo, text=True, stderr=subprocess.PIPE,
        ).strip()
    except subprocess.CalledProcessError as e:
        raise GitHubError(f"could not read 'origin' remote: {e.stderr}") from None

    slug = url
    if slug.endswith(".git"):
        slug = slug[:-4]
    if slug.startswith("git@"):           # git@github.com:owner/name
        slug = slug.split(":", 1)[-1]
    elif "github.com/" in slug:           # https://github.com/owner/name
        slug = slug.split("github.com/", 1)[-1]
    else:
        raise GitHubError(f"origin remote is not a github.com URL: {url}")
    parts = [p for p in slug.split("/") if p]
    if len(parts) < 2:
        raise GitHubError(f"could not parse owner/name from origin: {url}")
    return f"{parts[0]}/{parts[1]}"


def push_branch(target_repo: Path, branch: str) -> None:
    """Push the current HEAD to origin/<branch>. Assumes commits already made.

    Uses the git CLI (which uses the user's configured credentials/helper).
    The GITHUB_TOKEN is used only for the API call, not injected into git.
    """
    try:
        subprocess.check_output(
            ["git", "push", "-u", "origin", branch],
            cwd=target_repo, text=True, stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as e:
        raise GitHubError(f"git push failed for branch '{branch}': {e.output}") from None


def create_pull_request(
    target_repo: Path,
    *,
    head_branch: str,
    base_branch: str,
    title: str,
    body: str,
    draft: bool = True,
) -> dict[str, Any]:
    """Create a PR on the target repo's GitHub origin.

    Returns {"number", "html_url", "state", "draft"} on success.
    Raises GitHubError on any failure. Caller must have already gated on
    verifier=pass + governance approval.

    Default draft=True: the factory opens a DRAFT PR for human review rather
    than a ready-to-merge one. The factory never merges.
    """
    token = _token()
    slug = detect_repo_slug(target_repo)
    url = f"{_API}/repos/{slug}/pulls"
    payload = {
        "title": title,
        "head": head_branch,
        "base": base_branch,
        "body": body,
        "draft": draft,
    }
    log.info("creating PR on %s: %s -> %s (draft=%s)",
             slug, head_branch, base_branch, draft)
    resp = _api_request("POST", url, token, payload)
    result = {
        "number": resp.get("number"),
        "html_url": resp.get("html_url"),
        "state": resp.get("state"),
        "draft": resp.get("draft"),
        "repo": slug,
    }
    log.info("PR created: #%s %s", result["number"], result["html_url"])
    return result


def build_pr_body(run_record: dict[str, Any]) -> str:
    """Assemble a PR body from the run's verifier + agent reports.

    Pure string assembly — no network. The review/security/docs reports
    (v1.3 real agents) become the PR's evidence section.
    """
    v = run_record.get("verifier", {}) or {}
    rev = run_record.get("review_report", {}) or {}
    sec = run_record.get("security_report", {}) or {}
    docs = run_record.get("documentation_report", {}) or {}
    signal = run_record.get("signal", {}) or {}
    attempts = run_record.get("attempts_used", "?")

    lines = [
        f"## Software Factory run `{run_record.get('run_id', '?')}`",
        "",
        f"**Signal:** {signal.get('signal_id', '?')} — {signal.get('title', '')}",
        f"**Verifier decision:** `{v.get('decision', '?')}`  ",
        f"**Attempts used:** {attempts}  ",
        f"**Diff size:** {v.get('diff_size_bytes', 0)} bytes",
        "",
        "### Verifier",
        f"- tests_ok: {v.get('tests_ok')}",
        f"- security_ok: {v.get('security_ok')}",
        f"- review_ok: {v.get('review_ok')}",
        "",
        "### Review",
        f"- overall: **{rev.get('overall', '?')}** "
        f"({len(rev.get('findings', []))} findings)",
    ]
    for f in rev.get("findings", [])[:10]:
        lines.append(f"  - `{f.get('severity')}` {f.get('message')}")

    lines += [
        "",
        "### Security",
        f"- overall: **{sec.get('overall', '?')}** "
        f"({len(sec.get('issues', []))} issues)",
    ]
    for i in sec.get("issues", [])[:10]:
        lines.append(f"  - `{i.get('severity')}` {i.get('message')} ({i.get('file')})")

    lines += [
        "",
        "### Documentation",
        f"- overall: **{docs.get('overall', '?')}**, "
        f"gap: {docs.get('documentation_gap')}",
    ]
    for rec in docs.get("recommendations", [])[:5]:
        lines.append(f"  - {rec}")

    lines += [
        "",
        "---",
        "_Opened as a **draft** by the Software Factory. "
        "A human reviews and merges; the factory never merges._",
    ]
    return "\n".join(lines)
