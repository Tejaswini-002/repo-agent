#!/usr/bin/env python3
"""GitHub comment helper for PR summaries and review comments."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

BOT_NAME = os.getenv("REVIEW_BOT_NAME", "CodeRabbit")
BOT_ICON = os.getenv("REVIEW_BOT_ICON", "")
COMMENT_GREETING = f"{BOT_ICON} {BOT_NAME}".strip()

COMMENT_TAG = "<!-- auto-generated comment: pr review -->"
COMMENT_REPLY_TAG = "<!-- auto-generated reply: pr review -->"
SUMMARIZE_TAG = "<!-- auto-generated comment: pr summary -->"

RAW_SUMMARY_START_TAG = "<!-- auto-generated: raw summary start -->\n<!--"
RAW_SUMMARY_END_TAG = "-->\n<!-- auto-generated: raw summary end -->"

SHORT_SUMMARY_START_TAG = "<!-- auto-generated: short summary start -->\n<!--"
SHORT_SUMMARY_END_TAG = "-->\n<!-- auto-generated: short summary end -->"

COMMIT_ID_START_TAG = "<!-- commit_ids_reviewed_start -->"
COMMIT_ID_END_TAG = "<!-- commit_ids_reviewed_end -->"

DESCRIPTION_START_TAG = "<!-- auto-generated release notes start -->"
DESCRIPTION_END_TAG = "<!-- auto-generated release notes end -->"


class GitHubCommenter:
    """Lightweight GitHub API client for PR comments."""

    def __init__(self, github_token: Optional[str] = None):
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.base_url = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "repo-monitor-agent",
        }
        if self.github_token:
            self.headers["Authorization"] = f"token {self.github_token}"

        self.review_comments_buffer: List[Dict[str, Any]] = []

    def _request(self, method: str, url: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        try:
            response = requests.request(
                method,
                url,
                headers=self.headers,
                data=json.dumps(payload).encode("utf-8") if payload else None,
                timeout=30,
            )
            response.raise_for_status()
            return response.json() if response.text else {}
        except Exception as exc:
            logger.error("GitHub API error %s %s: %s", method, url, exc)
            raise

    def list_issue_comments(self, repo: str, pr_number: int) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/repos/{repo}/issues/{pr_number}/comments"
        return self._request("GET", url) or []

    def create_issue_comment(self, repo: str, pr_number: int, body: str) -> Dict[str, Any]:
        url = f"{self.base_url}/repos/{repo}/issues/{pr_number}/comments"
        return self._request("POST", url, {"body": body})

    def update_issue_comment(self, repo: str, comment_id: int, body: str) -> Dict[str, Any]:
        url = f"{self.base_url}/repos/{repo}/issues/comments/{comment_id}"
        return self._request("PATCH", url, {"body": body})

    def upsert_issue_comment_by_tag(self, repo: str, pr_number: int, body: str, tag: str) -> Dict[str, Any]:
        comments = self.list_issue_comments(repo, pr_number)
        for comment in comments:
            if tag in (comment.get("body") or ""):
                return self.update_issue_comment(repo, comment["id"], body)
        return self.create_issue_comment(repo, pr_number, body)

    def find_issue_comment_with_tag(self, repo: str, pr_number: int, tag: str) -> Optional[Dict[str, Any]]:
        comments = self.list_issue_comments(repo, pr_number)
        for comment in comments:
            if tag in (comment.get("body") or ""):
                return comment
        return None

    def list_review_comments(self, repo: str, pr_number: int) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/repos/{repo}/pulls/{pr_number}/comments"
        return self._request("GET", url) or []

    def delete_review_comment(self, repo: str, comment_id: int) -> None:
        url = f"{self.base_url}/repos/{repo}/pulls/comments/{comment_id}"
        self._request("DELETE", url)

    def list_reviews(self, repo: str, pr_number: int) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/repos/{repo}/pulls/{pr_number}/reviews"
        return self._request("GET", url) or []

    def delete_pending_review(self, repo: str, pr_number: int) -> None:
        try:
            reviews = self.list_reviews(repo, pr_number)
            pending = next((r for r in reviews if r.get("state") == "PENDING"), None)
            if pending:
                url = f"{self.base_url}/repos/{repo}/pulls/{pr_number}/reviews/{pending['id']}"
                self._request("DELETE", url)
        except Exception as exc:
            logger.warning("Failed to delete pending review: %s", exc)

    def buffer_review_comment(self, path: str, start_line: int, end_line: int, message: str) -> None:
        body = f"{COMMENT_GREETING}\n\n{message}\n\n{COMMENT_TAG}"
        self.review_comments_buffer.append(
            {"path": path, "start_line": start_line, "end_line": end_line, "message": body}
        )

    def submit_review(self, repo: str, pr_number: int, commit_id: str, status_msg: str) -> None:
        body = f"{COMMENT_GREETING}\n\n{status_msg}"
        comments_payload = []

        if self.review_comments_buffer:
            for comment in self.review_comments_buffer:
                comment_data: Dict[str, Any] = {
                    "path": comment["path"],
                    "body": comment["message"],
                    "line": comment["end_line"],
                }
                if comment["start_line"] != comment["end_line"]:
                    comment_data["start_line"] = comment["start_line"]
                    comment_data["start_side"] = "RIGHT"
                comments_payload.append(comment_data)

        try:
            for existing in self.list_review_comments(repo, pr_number):
                if COMMENT_TAG in (existing.get("body") or ""):
                    try:
                        self.delete_review_comment(repo, existing["id"])
                    except Exception as exc:
                        logger.warning("Failed to delete review comment: %s", exc)

            self.delete_pending_review(repo, pr_number)
            url = f"{self.base_url}/repos/{repo}/pulls/{pr_number}/reviews"
            payload = {
                "event": "COMMENT",
                "body": body,
                "commit_id": commit_id,
                "comments": comments_payload,
            }
            self._request("POST", url, payload)
        except Exception as exc:
            logger.warning("Failed to submit review: %s", exc)
            for comment in self.review_comments_buffer:
                try:
                    self.create_review_comment(
                        repo,
                        pr_number,
                        comment["message"],
                        commit_id,
                        comment["path"],
                        comment["end_line"],
                    )
                except Exception as inner_exc:
                    logger.warning("Failed to post comment fallback: %s", inner_exc)
        finally:
            self.review_comments_buffer = []

    def create_review_comment(
        self,
        repo: str,
        pr_number: int,
        body: str,
        commit_id: str,
        path: str,
        line: int,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/repos/{repo}/pulls/{pr_number}/comments"
        payload = {
            "body": body,
            "commit_id": commit_id,
            "path": path,
            "line": line,
            "side": "RIGHT",
        }
        return self._request("POST", url, payload)

    def reply_review_comment(
        self,
        repo: str,
        pr_number: int,
        body: str,
        in_reply_to: int,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/repos/{repo}/pulls/{pr_number}/comments"
        payload = {
            "body": f"{body}\n\n{COMMENT_REPLY_TAG}",
            "in_reply_to": in_reply_to,
        }
        return self._request("POST", url, payload)

    def get_all_commit_ids(self, repo: str, pr_number: int) -> List[str]:
        commits: List[str] = []
        page = 1
        while True:
            url = f"{self.base_url}/repos/{repo}/pulls/{pr_number}/commits"
            data = self._request("GET", f"{url}?per_page=100&page={page}") or []
            if not data:
                break
            commits.extend([c.get("sha") for c in data if c.get("sha")])
            page += 1
        return commits

    def get_content_within_tags(self, content: str, start_tag: str, end_tag: str) -> str:
        if start_tag not in content or end_tag not in content:
            return ""
        return content.split(start_tag, 1)[1].split(end_tag, 1)[0].strip()

    def remove_content_within_tags(self, content: str, start_tag: str, end_tag: str) -> str:
        if start_tag not in content or end_tag not in content:
            return content
        before = content.split(start_tag, 1)[0].rstrip()
        after = content.split(end_tag, 1)[1].lstrip()
        return f"{before}\n\n{after}".strip()

    def get_raw_summary(self, summary: str) -> str:
        return self.get_content_within_tags(summary, RAW_SUMMARY_START_TAG, RAW_SUMMARY_END_TAG)

    def get_short_summary(self, summary: str) -> str:
        return self.get_content_within_tags(summary, SHORT_SUMMARY_START_TAG, SHORT_SUMMARY_END_TAG)

    def get_reviewed_commit_ids_block(self, summary: str) -> str:
        return self.get_content_within_tags(summary, COMMIT_ID_START_TAG, COMMIT_ID_END_TAG)

    def get_reviewed_commit_ids(self, block: str) -> List[str]:
        return [line.strip() for line in block.splitlines() if line.strip()]

    def add_reviewed_commit_id(self, existing_block: str, commit_id: str) -> str:
        ids = self.get_reviewed_commit_ids(existing_block) if existing_block else []
        if commit_id and commit_id not in ids:
            ids.append(commit_id)
        body = "\n".join(ids)
        return f"{COMMIT_ID_START_TAG}\n{body}\n{COMMIT_ID_END_TAG}"

    def get_highest_reviewed_commit_id(self, all_commits: List[str], reviewed: List[str]) -> str:
        highest = ""
        for sha in all_commits:
            if sha in reviewed:
                highest = sha
        return highest

    def get_description(self, description: str) -> str:
        return self.remove_content_within_tags(description, DESCRIPTION_START_TAG, DESCRIPTION_END_TAG)

    def update_description(self, repo: str, pr_number: int, message: str) -> None:
        try:
            pr_url = f"{self.base_url}/repos/{repo}/pulls/{pr_number}"
            pr = self._request("GET", pr_url)
            body = pr.get("body") or ""
            description = self.get_description(body)
            clean_message = self.remove_content_within_tags(
                message,
                DESCRIPTION_START_TAG,
                DESCRIPTION_END_TAG,
            )
            new_description = (
                f"{description}\n\n{DESCRIPTION_START_TAG}\n{clean_message}\n{DESCRIPTION_END_TAG}".strip()
            )
            self._request("PATCH", pr_url, {"body": new_description})
        except Exception as exc:
            logger.warning("Failed to update PR description: %s", exc)

    def get_comment_chain(self, repo: str, pr_number: int, comment: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        comments = self.list_review_comments(repo, pr_number)
        by_id = {c.get("id"): c for c in comments}
        chain: List[Dict[str, Any]] = []
        current = comment
        top_level = comment
        while current:
            chain.append(current)
            parent_id = current.get("in_reply_to")
            if not parent_id:
                top_level = current
                break
            current = by_id.get(parent_id)
            if current is None:
                break
        chain = list(reversed(chain))
        chain_text = "\n".join(
            f"{c.get('user', {}).get('login', 'user')}: {c.get('body', '')}" for c in chain
        )
        return chain_text, top_level
