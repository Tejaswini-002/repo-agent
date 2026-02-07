#!/usr/bin/env python3
"""Analyze push events and summarize changes."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from src.github_pr_fetcher import GitHubPRAnalyzer
from src.llm_client import get_llm_client

logger = logging.getLogger(__name__)

DEFAULT_PUSH_PROMPT = """
You are analyzing a GitHub push event. Summarize what changed and provide an analysis.
Return JSON with keys:
- summary (string)
- key_changes (array of strings)
- impact_level (Low/Medium/High)
- files_changed (array of strings)
- stats (object with additions, deletions, files)

Repository: {repo}
Before: {before}
After: {after}
Commit Messages:
{commit_messages}

Changed Files (sample patches):
{patches}
""".strip()


class PushAnalysisService:
    def __init__(self, model: str = "llama3", github_token: Optional[str] = None):
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.analyzer = GitHubPRAnalyzer(self.github_token)
        self.prompt = os.getenv("PUSH_ANALYSIS_PROMPT", DEFAULT_PUSH_PROMPT)
        self.llm = get_llm_client(model=model, temperature=0.2, max_tokens=1800)

    def _parse_json(self, text: str) -> Dict[str, Any]:
        try:
            match = re.search(r"\{[\s\S]*\}", text)
            if match:
                return json.loads(match.group(0))
            return json.loads(text)
        except Exception:
            return {
                "summary": text[:500],
                "key_changes": [],
                "impact_level": "Medium",
                "files_changed": [],
                "stats": {},
            }

    async def analyze_push(self, repo: str, before: str, after: str, commits: List[Dict[str, Any]]) -> Dict[str, Any]:
        compare = self.analyzer.compare_branches(repo, before, after) or {}
        files = compare.get("files", []) or []

        patches = []
        for f in files[:15]:
            filename = f.get("filename", "")
            patch = f.get("patch", "")
            if filename and patch:
                patches.append(f"--- {filename}\n{patch}")
        patch_text = "\n\n".join(patches)[:8000]

        commit_messages = "\n".join(
            f"- {c.get('id', '')[:7]} {c.get('message', '').splitlines()[0]}" for c in commits
        )

        prompt = self.prompt.format(
            repo=repo,
            before=before,
            after=after,
            commit_messages=commit_messages or "(none)",
            patches=patch_text or "(no patches)",
        )

        content = await self.llm.invoke(prompt)
        data = self._parse_json(content)
        data.setdefault("files_changed", [f.get("filename") for f in files if f.get("filename")])
        additions = sum(f.get("additions", 0) for f in files)
        deletions = sum(f.get("deletions", 0) for f in files)
        data.setdefault(
            "stats",
            {
                "additions": additions,
                "deletions": deletions,
                "files": len(files),
            },
        )
        return data
