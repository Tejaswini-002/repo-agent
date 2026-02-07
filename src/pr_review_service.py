#!/usr/bin/env python3
"""PR review service aligned with CodeRabbit-style workflow."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from src.github_commenter import (
    GitHubCommenter,
    SUMMARIZE_TAG,
    RAW_SUMMARY_START_TAG,
    RAW_SUMMARY_END_TAG,
    SHORT_SUMMARY_START_TAG,
    SHORT_SUMMARY_END_TAG,
    COMMENT_TAG,
    COMMENT_REPLY_TAG,
)
from src.github_pr_fetcher import GitHubPRAnalyzer
from src.llm_client import get_llm_client

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_MESSAGE = "You are a senior code reviewer. Be concise and actionable."

DEFAULT_FILE_SUMMARY_PROMPT = """
Summarize this file diff in <= 100 words.
Return JSON with keys: summary (string), triage (NEEDS_REVIEW or APPROVED).

PR Title: {title}
PR Description: {description}
File: {path}
Diff:
{diff}
""".strip()

DEFAULT_SUMMARIZE_CHANGES_PROMPT = """
You are given file-level summaries. Merge related changesets and de-duplicate.
Return the updated changesets using the same format.

Changesets:
{raw_summary}
""".strip()

DEFAULT_SUMMARY_PROMPT = """
Provide a clear summary of the PR in 2-4 sentences.
Use the provided changesets.

Changesets:
{raw_summary}
""".strip()

DEFAULT_RELEASE_NOTES_PROMPT = """
Create concise release notes as bullet points based on the changesets.
Return JSON with key: release_notes (array of strings).

Changesets:
{raw_summary}
""".strip()

DEFAULT_SHORT_SUMMARY_PROMPT = """
Provide a short summary (2-4 sentences) for reviewers to use as context.

Changesets:
{raw_summary}
""".strip()

DEFAULT_REVIEW_PROMPT = """
Review the new hunks for substantive issues only. Use the short summary for context.
Return a JSON array of comments. Each comment must include: path, start_line, end_line, comment.
If no issues, return an empty array [].

System: {system_message}
File: {path}
Short summary:
{short_summary}
Numbered hunks:
{numbered_hunks}
""".strip()

DEFAULT_CHAT_PROMPT = """
You are replying to a PR review comment with requested guidance.
Be concise and specific. Reply in 2-6 sentences.

PR Title: {title}
File: {path}
Diff Hunk:
{diff_hunk}
Comment Chain:
{comment_chain}
""".strip()


@dataclass
class ReviewResult:
    summary: str
    release_notes: List[str]
    raw_summary: str
    short_summary: str
    review_comments: List[Dict[str, Any]]
    reviewed_sha: str
    skipped: bool
    skip_reason: str


class PRReviewService:
    """Generate summaries, release notes, and inline review comments."""

    def __init__(
        self,
        light_model: str = "llama3",
        heavy_model: str = "llama3",
        github_token: Optional[str] = None,
        review_simple_changes: bool = False,
        simple_change_threshold: int = 20,
        skip_extensions: Optional[List[str]] = None,
    ):
        self.light_model = light_model
        self.heavy_model = heavy_model
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.commenter = GitHubCommenter(self.github_token)
        self.analyzer = GitHubPRAnalyzer(self.github_token)
        self.review_simple_changes = review_simple_changes
        self.simple_change_threshold = simple_change_threshold
        self.skip_extensions = skip_extensions or ["md", "txt", "rst", "png", "jpg", "jpeg", "gif"]
        self.review_comment_lgtm = os.getenv("REVIEW_COMMENT_LGTM", "0") == "1"
        self.max_files = int(os.getenv("REVIEW_MAX_FILES", "0"))
        self.ignore_keyword = os.getenv("REVIEW_IGNORE_KEYWORD", "@coderabbitai: ignore")
        self.update_description = os.getenv("REVIEW_UPDATE_DESCRIPTION", "1") == "1"

        self.system_message = os.getenv("REVIEW_SYSTEM_MESSAGE", DEFAULT_SYSTEM_MESSAGE)
        self.file_summary_prompt = os.getenv("REVIEW_FILE_SUMMARY_PROMPT", DEFAULT_FILE_SUMMARY_PROMPT)
        self.summarize_changes_prompt = os.getenv(
            "REVIEW_SUMMARIZE_CHANGESETS_PROMPT", DEFAULT_SUMMARIZE_CHANGES_PROMPT
        )
        self.summary_prompt = os.getenv("REVIEW_SUMMARY_PROMPT", DEFAULT_SUMMARY_PROMPT)
        self.release_notes_prompt = os.getenv(
            "REVIEW_RELEASE_NOTES_PROMPT", DEFAULT_RELEASE_NOTES_PROMPT
        )
        self.short_summary_prompt = os.getenv("REVIEW_SHORT_SUMMARY_PROMPT", DEFAULT_SHORT_SUMMARY_PROMPT)
        self.review_prompt = os.getenv("REVIEW_FILE_PROMPT", DEFAULT_REVIEW_PROMPT)
        self.chat_prompt = os.getenv("REVIEW_CHAT_PROMPT", DEFAULT_CHAT_PROMPT)

        self.light_llm = get_llm_client(self.light_model, temperature=0.2, max_tokens=1200)
        self.heavy_llm = get_llm_client(self.heavy_model, temperature=0.2, max_tokens=2000)

    def _should_skip_review(self, files: List[Dict[str, Any]]) -> Tuple[bool, str]:
        total_changes = sum((f.get("additions", 0) + f.get("deletions", 0)) for f in files)
        extensions = {f.get("filename", "").split(".")[-1].lower() for f in files if f.get("filename")}
        if not self.review_simple_changes and total_changes <= self.simple_change_threshold:
            return True, f"simple changes (<= {self.simple_change_threshold} lines)"
        if extensions and extensions.issubset(set(self.skip_extensions)):
            return True, "documentation-only changes"
        return False, ""

    def _extract_numbered_hunks(self, patch: str) -> str:
        if not patch:
            return ""
        numbered_lines: List[str] = []
        new_line = 0
        for line in patch.splitlines():
            if line.startswith("@@"):
                match = re.search(r"\+(\d+)", line)
                new_line = int(match.group(1)) if match else 0
                numbered_lines.append(line)
                continue
            if line.startswith("+"):
                numbered_lines.append(f"{new_line}:+{line[1:]}")
                new_line += 1
            elif line.startswith("-"):
                numbered_lines.append(f"-: {line[1:]}")
            else:
                numbered_lines.append(f"{new_line}: {line[1:] if line.startswith(' ') else line}")
                new_line += 1
        return "\n".join(numbered_lines)

    def _parse_json(self, text: str, default: Any) -> Any:
        try:
            match = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", text)
            if match:
                return json.loads(match.group(0))
            return json.loads(text)
        except Exception:
            return default

    async def _run_file_summary(self, pr_details: Dict[str, Any], path: str, diff_text: str) -> Tuple[str, str]:
        prompt = self.file_summary_prompt.format(
            title=pr_details.get("title", ""),
            description=(pr_details.get("body") or "")[:2000],
            path=path,
            diff=diff_text,
        )
        content = await self.light_llm.invoke(prompt)
        data = self._parse_json(content, {"summary": content[:300], "triage": "NEEDS_REVIEW"})
        summary = data.get("summary", "")
        triage = data.get("triage", "NEEDS_REVIEW")
        return summary, triage

    async def _run_summary(self, raw_summary: str) -> Tuple[str, List[str], str]:
        changes_prompt = self.summarize_changes_prompt.format(raw_summary=raw_summary)
        combined = await self.heavy_llm.invoke(changes_prompt)
        if combined:
            raw_summary = combined

        summary_prompt = self.summary_prompt.format(raw_summary=raw_summary)
        summary = await self.heavy_llm.invoke(summary_prompt)

        release_prompt = self.release_notes_prompt.format(raw_summary=raw_summary)
        release_response = await self.heavy_llm.invoke(release_prompt)
        release_data = self._parse_json(release_response, {"release_notes": []})
        release_notes = release_data.get("release_notes", []) if isinstance(release_data, dict) else []

        short_prompt = self.short_summary_prompt.format(raw_summary=raw_summary)
        short_summary = await self.heavy_llm.invoke(short_prompt)

        return summary.strip(), release_notes, short_summary.strip()

    async def _run_file_review(self, path: str, patch: str, short_summary: str) -> List[Dict[str, Any]]:
        numbered_hunks = self._extract_numbered_hunks(patch)
        if not numbered_hunks.strip():
            return []
        prompt = self.review_prompt.format(
            system_message=self.system_message,
            path=path,
            short_summary=short_summary,
            numbered_hunks=numbered_hunks,
        )
        content = await self.heavy_llm.invoke(prompt)
        data = self._parse_json(content, [])
        if isinstance(data, list):
            normalized: List[Dict[str, Any]] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                if not item.get("path"):
                    item["path"] = path
                if "line" in item and "end_line" not in item:
                    item["end_line"] = item.get("line")
                if "start_line" not in item and "end_line" in item:
                    item["start_line"] = item.get("end_line")
                normalized.append(item)
            return normalized
        return []

    async def review_pr(self, repo: str, pr_number: int) -> ReviewResult:
        pr_details = self.analyzer.get_pr_details(repo, pr_number)
        if not pr_details:
            return ReviewResult("", [], "", "", [], "", True, "failed to fetch PR details")

        description = pr_details.get("body") or ""
        if self.ignore_keyword and self.ignore_keyword in description:
            return ReviewResult("", [], "", "", [], "", True, "ignored by keyword")

        head_sha = pr_details.get("head", {}).get("sha")
        base_sha = pr_details.get("base", {}).get("sha")
        existing_summary = self.commenter.find_issue_comment_with_tag(repo, pr_number, SUMMARIZE_TAG)
        existing_body = existing_summary.get("body", "") if existing_summary else ""
        existing_block = self.commenter.get_reviewed_commit_ids_block(existing_body)
        reviewed_ids = self.commenter.get_reviewed_commit_ids(existing_block)

        all_commits = self.commenter.get_all_commit_ids(repo, pr_number) if self.github_token else []
        highest_reviewed = self.commenter.get_highest_reviewed_commit_id(all_commits, reviewed_ids)
        compare_base = highest_reviewed or base_sha
        compare = self.analyzer.compare_branches(repo, compare_base, head_sha)
        if not compare:
            return ReviewResult("", [], "", "", [], head_sha or "", True, "failed to compare commits")

        files = compare.get("files", []) or []
        if not files:
            return ReviewResult("", [], "", "", [], head_sha or "", True, "no files to review")

        skipped, reason = self._should_skip_review(files)
        skip_reviews = skipped and reason == "documentation-only changes"
        simple_reason = reason if skipped else ""

        summaries: List[Tuple[str, str, str]] = []
        skipped_files: List[str] = []
        for file in files:
            path = file.get("filename")
            patch = file.get("patch")
            if not path or not patch:
                continue
            ext = path.split(".")[-1].lower() if "." in path else ""
            if ext in self.skip_extensions:
                skipped_files.append(path)
                continue
            summary, triage = await self._run_file_summary(pr_details, path, patch)
            summaries.append((path, summary, triage))
            if self.max_files > 0 and len(summaries) >= self.max_files:
                break

        raw_summary = "\n".join(f"{path}: {summary}" for path, summary, _ in summaries)
        summary, release_notes, short_summary = await self._run_summary(raw_summary)

        review_comments: List[Dict[str, Any]] = []
        if skip_reviews:
            return ReviewResult(
                summary,
                release_notes,
                raw_summary,
                short_summary,
                review_comments,
                head_sha or "",
                False,
                "",
            )

        for file in files:
            path = file.get("filename")
            patch = file.get("patch")
            if not path or not patch:
                continue
            triage = next((t for p, _, t in summaries if p == path), "NEEDS_REVIEW")
            if not self.review_simple_changes and simple_reason:
                continue
            if not self.review_simple_changes and triage == "APPROVED":
                continue
            comments = await self._run_file_review(path, patch, short_summary)
            review_comments.extend(comments)

        return ReviewResult(
            summary,
            release_notes,
            raw_summary,
            short_summary,
            review_comments,
            head_sha or "",
            False,
            "",
        )

    def _build_summary_comment(
        self,
        summary: str,
        release_notes: List[str],
        raw_summary: str,
        short_summary: str,
        commit_id_block: str,
    ) -> str:
        notes = "\n".join(f"- {n}" for n in release_notes) if release_notes else "- (none)"
        return (
            f"{SUMMARIZE_TAG}\n"
            f"### Summary\n\n{summary}\n\n"
            f"### Release Notes\n{notes}\n\n"
            f"{RAW_SUMMARY_START_TAG}\n{raw_summary}\n{RAW_SUMMARY_END_TAG}\n"
            f"{SHORT_SUMMARY_START_TAG}\n{short_summary}\n{SHORT_SUMMARY_END_TAG}\n\n"
            f"{commit_id_block}\n"
        )

    async def post_review(self, repo: str, pr_number: int) -> ReviewResult:
        result = await self.review_pr(repo, pr_number)
        if result.skipped:
            logger.info("Review skipped for %s#%s: %s", repo, pr_number, result.skip_reason)
            return result

        if not self.github_token:
            logger.warning("GitHub token missing. Review generated but not posted.")
            return result

        pr_details = self.analyzer.get_pr_details(repo, pr_number) or {}
        commit_id = pr_details.get("head", {}).get("sha")

        existing_summary = self.commenter.find_issue_comment_with_tag(repo, pr_number, SUMMARIZE_TAG)
        existing_body = existing_summary.get("body", "") if existing_summary else ""
        existing_block = self.commenter.get_reviewed_commit_ids_block(existing_body)
        commit_id_block = self.commenter.add_reviewed_commit_id(existing_block, result.reviewed_sha)

        summary_body = self._build_summary_comment(
            result.summary,
            result.release_notes,
            result.raw_summary,
            result.short_summary,
            commit_id_block,
        )
        self.commenter.upsert_issue_comment_by_tag(repo, pr_number, summary_body, SUMMARIZE_TAG)

        if self.update_description and result.release_notes:
            release_message = "\n".join(f"- {n}" for n in result.release_notes)
            self.commenter.update_description(repo, pr_number, release_message)

        if commit_id and result.review_comments:
            max_comments = int(os.getenv("REVIEW_MAX_COMMENTS", "20"))
            for comment in result.review_comments[:max_comments]:
                path = comment.get("path") or ""
                start_line = int(comment.get("start_line", 0) or 0)
                end_line = int(comment.get("end_line", 0) or 0)
                message = comment.get("comment") or ""
                if not path or not message or end_line <= 0:
                    continue
                if not self.review_comment_lgtm and "LGTM" in message:
                    continue
                self.commenter.buffer_review_comment(path, start_line or end_line, end_line, message)
            self.commenter.submit_review(repo, pr_number, commit_id, "Review completed")

        return result

    async def handle_review_comment_event(self, event: Dict[str, Any]) -> None:
        action = event.get("action")
        if action != "created":
            return
        comment = event.get("comment", {})
        if not comment:
            return
        body = comment.get("body", "") or ""
        if COMMENT_TAG in body or COMMENT_REPLY_TAG in body:
            return

        mention = os.getenv("REVIEW_BOT_MENTION", "@coderabbitai")
        pull = event.get("pull_request", {})
        repo = event.get("repository", {}).get("full_name")
        pr_number = pull.get("number")
        if not repo or not pr_number:
            return

        comment_chain, top_level = self.commenter.get_comment_chain(repo, pr_number, comment)
        if mention not in body and mention not in comment_chain:
            return

        pr_title = pull.get("title", "")
        diff_hunk = comment.get("diff_hunk", "")
        path = comment.get("path", "")

        prompt = self.chat_prompt.format(
            title=pr_title,
            path=path,
            diff_hunk=diff_hunk,
            comment_chain=comment_chain,
        )
        content = await self.heavy_llm.invoke(prompt)

        if self.github_token and top_level:
            reply_text = content.strip()[:2000]
            user = comment.get("user", {}).get("login", "user")
            self.commenter.reply_review_comment(
                repo,
                pr_number,
                f"@{user} {reply_text}",
                top_level.get("id"),
            )
