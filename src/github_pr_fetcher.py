#!/usr/bin/env python3
"""
GitHub API Integration for PR Code Analysis
Fetches PR diffs, file changes, and compares branches
"""

import os
import requests
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


class GitHubPRAnalyzer:
    """Fetch and analyze PR code changes from GitHub"""
    
    def __init__(self, github_token: Optional[str] = None):
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.base_url = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        if self.github_token:
            self.headers["Authorization"] = f"token {self.github_token}"
    
    def get_pr_details(self, repo: str, pr_number: int) -> Optional[Dict[str, Any]]:
        """Get PR details including files changed and diff"""
        url = f"{self.base_url}/repos/{repo}/pulls/{pr_number}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch PR details: {e}")
            return None
    
    def get_pr_files(self, repo: str, pr_number: int) -> List[Dict[str, Any]]:
        """Get list of files changed in PR with patches"""
        url = f"{self.base_url}/repos/{repo}/pulls/{pr_number}/files"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch PR files: {e}")
            return []
    
    def get_pr_diff(self, repo: str, pr_number: int) -> Optional[str]:
        """Get full PR diff"""
        url = f"{self.base_url}/repos/{repo}/pulls/{pr_number}"
        headers = {**self.headers, "Accept": "application/vnd.github.v3.diff"}
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Failed to fetch PR diff: {e}")
            return None
    
    def compare_branches(self, repo: str, base: str, head: str) -> Optional[Dict[str, Any]]:
        """Compare two branches/commits"""
        url = f"{self.base_url}/repos/{repo}/compare/{base}...{head}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to compare branches: {e}")
            return None
    
    def get_file_content(self, repo: str, path: str, ref: str = "main") -> Optional[str]:
        """Get content of a specific file at a ref"""
        url = f"{self.base_url}/repos/{repo}/contents/{path}"
        params = {"ref": ref}
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Decode base64 content
            import base64
            content = base64.b64decode(data["content"]).decode("utf-8")
            return content
        except Exception as e:
            logger.error(f"Failed to fetch file content: {e}")
            return None
    
    def analyze_pr_changes(self, repo: str, pr_number: int) -> Dict[str, Any]:
        """
        Comprehensive PR analysis with code diff
        Returns structured data for LLM analysis
        """
        pr_details = self.get_pr_details(repo, pr_number)
        if not pr_details:
            return {"error": "Failed to fetch PR details"}
        
        pr_files = self.get_pr_files(repo, pr_number)
        pr_diff = self.get_pr_diff(repo, pr_number)
        
        # Categorize changes
        files_by_type = {
            "added": [],
            "modified": [],
            "removed": [],
            "renamed": []
        }
        
        language_stats = {}
        total_additions = 0
        total_deletions = 0
        
        for file in pr_files:
            status = file.get("status", "modified")
            filename = file.get("filename", "")
            
            # Get file extension
            ext = filename.split(".")[-1] if "." in filename else "unknown"
            language_stats[ext] = language_stats.get(ext, 0) + 1
            
            # Track additions/deletions
            total_additions += file.get("additions", 0)
            total_deletions += file.get("deletions", 0)
            
            # Categorize by status
            file_info = {
                "filename": filename,
                "additions": file.get("additions", 0),
                "deletions": file.get("deletions", 0),
                "changes": file.get("changes", 0),
                "patch": file.get("patch", "")[:500]  # First 500 chars
            }
            
            if status in files_by_type:
                files_by_type[status].append(file_info)
        
        return {
            "pr_number": pr_number,
            "title": pr_details.get("title", ""),
            "body": pr_details.get("body", "")[:1000],  # First 1000 chars
            "state": pr_details.get("state", ""),
            "author": pr_details.get("user", {}).get("login", ""),
            "base_branch": pr_details.get("base", {}).get("ref", ""),
            "head_branch": pr_details.get("head", {}).get("ref", ""),
            "created_at": pr_details.get("created_at", ""),
            "updated_at": pr_details.get("updated_at", ""),
            "commits": pr_details.get("commits", 0),
            "files_changed": len(pr_files),
            "additions": total_additions,
            "deletions": total_deletions,
            "files_by_type": files_by_type,
            "language_stats": language_stats,
            "full_diff": pr_diff[:5000] if pr_diff else None,  # First 5000 chars
        }


def create_pr_summary_prompt(pr_data: Dict[str, Any]) -> str:
    """Create detailed prompt for LLM analysis with actual code changes"""
    
    prompt = f"""Analyze this GitHub Pull Request in detail:

**PR Information:**
- Number: #{pr_data['pr_number']}
- Title: {pr_data['title']}
- Author: {pr_data['author']}
- Branch: {pr_data['head_branch']} → {pr_data['base_branch']}
- State: {pr_data['state']}

**Changes Summary:**
- Files Changed: {pr_data['files_changed']}
- Total Additions: {pr_data['additions']} lines
- Total Deletions: {pr_data['deletions']} lines
- Commits: {pr_data['commits']}

**Files by Type:**
"""
    
    for change_type, files in pr_data.get('files_by_type', {}).items():
        if files:
            prompt += f"\n{change_type.upper()} ({len(files)} files):\n"
            for f in files[:5]:  # Show first 5
                prompt += f"  - {f['filename']} (+{f['additions']}/-{f['deletions']})\n"
    
    prompt += f"\n**Language Distribution:**\n"
    for lang, count in pr_data.get('language_stats', {}).items():
        prompt += f"  - {lang}: {count} files\n"
    
    if pr_data.get('body'):
        prompt += f"\n**PR Description:**\n{pr_data['body']}\n"
    
    if pr_data.get('full_diff'):
        prompt += f"\n**Code Changes (Sample):**\n```diff\n{pr_data['full_diff']}\n```\n"
    
    prompt += """
**Your Task:**
Analyze this PR and provide:

1. **Summary** (2-3 sentences): What does this PR accomplish?

2. **Key Changes** (3-5 bullet points): What are the main modifications?

3. **Impact Assessment**: 
   - Impact Level: Low/Medium/High
   - Reasoning: Why this level?

4. **Code Quality Observations**:
   - What's done well?
   - Any concerns or potential issues?

5. **Suggestions** (3-5 items):
   - Testing recommendations
   - Documentation needs
   - Potential improvements
   - Security considerations (if applicable)

6. **Recommended Actions** (2-4 items):
   - Specific next steps for reviewers
   - Areas requiring extra attention

Format as JSON with keys: summary, key_changes, impact_level, impact_reasoning, code_quality, suggestions, recommended_actions
"""
    
    return prompt
