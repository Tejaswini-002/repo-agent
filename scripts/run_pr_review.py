#!/usr/bin/env python3
"""Run PR review based on GitHub Actions event payload."""

import asyncio
import json
import os
from pathlib import Path

from src.pr_review_service import PRReviewService


def load_event() -> dict:
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path:
        raise RuntimeError("GITHUB_EVENT_PATH not set")
    return json.loads(Path(event_path).read_text(encoding="utf-8"))


async def main():
    event_name = os.getenv("GITHUB_EVENT_NAME", "")
    event = load_event()

    service = PRReviewService(
        light_model=os.getenv("REVIEW_LIGHT_MODEL", os.getenv("FOUNDRY_LOCAL_MODEL", "llama3")),
        heavy_model=os.getenv("REVIEW_HEAVY_MODEL", os.getenv("FOUNDRY_LOCAL_MODEL", "llama3")),
        github_token=os.getenv("GITHUB_TOKEN"),
        review_simple_changes=os.getenv("REVIEW_SIMPLE_CHANGES", "0") == "1",
        simple_change_threshold=int(os.getenv("REVIEW_SIMPLE_THRESHOLD", "20")),
    )

    if event_name == "pull_request":
        repo = event.get("repository", {}).get("full_name")
        pr_number = event.get("pull_request", {}).get("number")
        if not repo or not pr_number:
            raise RuntimeError("Missing repo or PR number in event payload")
        await service.post_review(repo, pr_number)
        return

    if event_name == "pull_request_review_comment":
        await service.handle_review_comment_event(event)
        return

    print(f"Skipped unsupported event: {event_name}")


if __name__ == "__main__":
    asyncio.run(main())
