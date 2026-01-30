#!/usr/bin/env python3
"""Post a simple confirmation comment on a PR (no LLM).

Runs ONLY in GitHub Actions on pull_request events.

Requires env:
- GITHUB_TOKEN (provided by Actions)
- GITHUB_REPOSITORY (owner/repo)
- PR_NUMBER
- GITHUB_SHA
"""

import os
import json
import urllib.request

def must(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def is_dry_run() -> bool:
    v = os.getenv("DRY_RUN")
    return v is not None and v != "0"

def post_comment(repo: str, pr_number: str, token: str, body: str):
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    payload = json.dumps({"body": body}).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "repo-monitor-agent")

    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"GitHub API returned {resp.status}: {resp.read().decode('utf-8', errors='ignore')}")

def main():
    if is_dry_run():
        repo = os.getenv("GITHUB_REPOSITORY", "<owner/repo>")
        pr_number = os.getenv("PR_NUMBER", "<pr-number>")
        sha = os.getenv("GITHUB_SHA", "(local)")
        body = (
            "## ✅ Repo Monitor Agent\n"
            "(dry-run) Would post the following comment:\n\n"
            f"- Commit: `{sha}`\n"
            "- What I checked: latest commit + changed files (see Actions logs)\n"
        )
        print(f"DRY RUN - would post to {repo} PR #{pr_number}:\n\n{body}")
        return

    token = must("GITHUB_TOKEN")
    repo = must("GITHUB_REPOSITORY")
    pr_number = must("PR_NUMBER")
    sha = os.getenv("GITHUB_SHA", "")

    body = (
        "## ✅ Repo Monitor Agent\n"
        "I ran successfully on this PR update.\n\n"
        f"- Commit: `{sha}`\n"
        "- What I checked: latest commit + changed files (see Actions logs)\n"
    )

    post_comment(repo, pr_number, token, body)
    print(f"Commented on PR #{pr_number}")

if __name__ == "__main__":
    main()
