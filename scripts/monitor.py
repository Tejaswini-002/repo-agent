#!/usr/bin/env python3
"""Repo Monitor Agent (no LLM)

What it does:
- Prints the triggering event info (push or pull_request)
- Prints last commit metadata
- Prints files changed in the last commit (name + status)
- Optionally prints a short diff summary (first N lines)

This script is used both:
- Locally (you can run it in a cloned repo)
- In GitHub Actions (as the monitoring job)
"""

import os
import subprocess
import json
from datetime import datetime
from typing import List

def sh(cmd: str) -> str:
    return subprocess.check_output(cmd, shell=True, text=True).strip()

def have_prev_commit() -> bool:
    try:
        sh("git rev-parse HEAD~1")
        return True
    except Exception:
        return False

def print_header(title: str):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)

def main():
    print_header("Repo Monitor Agent (no LLM)")

    event_name = os.getenv("GITHUB_EVENT_NAME", "(local)")
    repo = os.getenv("GITHUB_REPOSITORY", "(local)")
    ref = os.getenv("GITHUB_REF", "(local)")
    sha = os.getenv("GITHUB_SHA", sh("git rev-parse HEAD"))
    events_path = os.getenv("MONITOR_EVENTS_PATH", "repo-monitor-events.jsonl")

    print(f"Event: {event_name}")
    print(f"Repo:  {repo}")
    print(f"Ref:   {ref}")
    print(f"SHA:   {sha}")

    print_header("Latest commit")
    try:
        print(sh("git log -1 --pretty=fuller"))
    except Exception as e:
        print("Could not read git log. Are you inside a git repo?")
        raise

    print_header("Changed files (last commit)")
    if have_prev_commit():
        print(sh("git diff --name-status HEAD~1..HEAD"))
    else:
        # first commit case
        print("(no previous commit - showing files in initial commit)")
        print(sh("git show --name-status --pretty='' HEAD"))

    print_header("Diff summary (first 120 lines)")
    try:
        if have_prev_commit():
            diff_text = subprocess.check_output("git diff --stat HEAD~1..HEAD", shell=True, text=True)
        else:
            diff_text = subprocess.check_output("git show --stat --pretty='' HEAD", shell=True, text=True)
        print(diff_text.strip())
    except Exception as e:
        print("Could not generate diff summary:", e)

    # Build event record and append to JSONL file so Actions can upload it as an artifact
    event = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event_name": event_name,
        "repo": repo,
        "ref": ref,
        "sha": sha,
        "latest_commit": None,
        "changed_files": None,
        "diff_stat": None,
    }

    try:
        event["latest_commit"] = sh("git log -1 --pretty=fuller")
    except Exception:
        event["latest_commit"] = "(unavailable)"

    try:
        if have_prev_commit():
            event["changed_files"] = sh("git diff --name-status HEAD~1..HEAD")
        else:
            event["changed_files"] = sh("git show --name-status --pretty='' HEAD")
    except Exception:
        event["changed_files"] = "(unavailable)"

    try:
        if have_prev_commit():
            event["diff_stat"] = subprocess.check_output("git diff --stat HEAD~1..HEAD", shell=True, text=True).strip()
        else:
            event["diff_stat"] = subprocess.check_output("git show --stat --pretty='' HEAD", shell=True, text=True).strip()
    except Exception:
        event["diff_stat"] = "(unavailable)"

    try:
        with open(events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        print(f"Wrote event to {events_path}")
    except Exception as e:
        print("Could not write event file:", e)

    print("\nDone ✅")

if __name__ == "__main__":
    main()
