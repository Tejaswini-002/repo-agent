#!/usr/bin/env python3
"""
PR Intelligence Engine - Analyzes PR events and generates actionable insights
using LLM to suggest improvements and changes to the repository.
"""

import json
import os
import asyncio
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.llm_client import get_llm_client

logger = logging.getLogger(__name__)

# Import GitHub PR Fetcher
try:
    from src.github_pr_fetcher import GitHubPRAnalyzer, create_pr_summary_prompt
except ImportError:
    try:
        from github_pr_fetcher import GitHubPRAnalyzer, create_pr_summary_prompt
    except ImportError:
        GitHubPRAnalyzer = None
        create_pr_summary_prompt = None

def _get_llm(model: str = "llama3"):
    """Get LLM client (Ollama or Foundry Local)"""
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "2000"))
    return get_llm_client(model=model, temperature=temperature, max_tokens=max_tokens)


@dataclass
class PRAnalysisResult:
    """Result of PR analysis"""
    pr_number: int
    pr_title: str
    files_changed: int
    summary: str
    key_changes: List[str]
    impact_level: str  # Low, Medium, High
    suggestions: List[str]
    improvement_areas: List[str]
    recommended_actions: List[Dict[str, str]]
    timestamp: str


class SuggestionModel(BaseModel):
    """Structured suggestion response"""
    key_changes: List[str] = Field(description="Main changes in this PR")
    summary: str = Field(description="2-3 sentence summary of the PR")
    impact_level: str = Field(description="Impact level: Low, Medium, or High")
    suggestions: List[str] = Field(description="3-5 suggestions for improvement")
    improvement_areas: List[str] = Field(description="Areas that could be better")
    recommended_actions: List[Dict[str, str]] = Field(
        description="List of {action: description} recommendations"
    )


class PRIntelligenceEngine:
    """Analyzes PR events and generates suggestions"""
    
    def __init__(self, model: str = "llama3", github_token: Optional[str] = None):
        self.llm = _get_llm(model)
        self.model = model
        self.github_analyzer = GitHubPRAnalyzer(github_token) if GitHubPRAnalyzer else None
        
    async def analyze_pr_with_code(self, repo: str, pr_number: int) -> PRAnalysisResult:
        """
        Analyze PR by fetching actual code changes from GitHub
        This provides much deeper analysis than just metadata
        """
        if not self.github_analyzer:
            raise ValueError("GitHub analyzer not available. Install requests: pip install requests")
        
        # Fetch comprehensive PR data with code diffs
        pr_data = self.github_analyzer.analyze_pr_changes(repo, pr_number)
        
        if "error" in pr_data:
            raise ValueError(f"Failed to fetch PR: {pr_data['error']}")
        
        # Create detailed prompt with actual code changes
        prompt_text = create_pr_summary_prompt(pr_data)
        
        # Run LLM analysis
        try:
            content = await self.llm.invoke(prompt_text)
            
            # Extract JSON from response
            try:
                import re
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    data = json.loads(json_match.group())
                else:
                    data = json.loads(content)
            except:
                # Fallback parsing
                data = {
                    "summary": content[:500],
                    "key_changes": ["Unable to parse structured response"],
                    "impact_level": "Medium",
                    "suggestions": ["Review the raw analysis output"],
                    "improvement_areas": [],
                    "recommended_actions": []
                }
            
            # Build result
            return PRAnalysisResult(
                pr_number=pr_number,
                pr_title=pr_data.get("title", "Unknown"),
                files_changed=pr_data.get("files_changed", 0),
                summary=data.get("summary", ""),
                key_changes=data.get("key_changes", []),
                impact_level=data.get("impact_level", "Medium"),
                suggestions=data.get("suggestions", []),
                improvement_areas=data.get("improvement_areas", []),
                recommended_actions=data.get("recommended_actions", []),
                timestamp=datetime.utcnow().isoformat()
            )
        
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            raise
        
    async def analyze_pr_event(self, pr_data: Dict[str, Any]) -> PRAnalysisResult:
        """Analyze a single PR event and generate suggestions"""
        
        # Extract PR info
        summary = pr_data.get("summary", {})
        if not summary:
            return None
            
        pr_number = summary.get("pr_number", "unknown")
        pr_title = summary.get("title", "Untitled")
        files_changed = summary.get("changed_files_count", 0)
        repo = summary.get("repo", "unknown")
        
        # Create analysis prompt
        analysis_prompt = ChatPromptTemplate.from_template("""
Analyze this GitHub Pull Request and provide actionable insights:

**PR Details:**
- Number: {pr_number}
- Title: {pr_title}
- Repository: {repo}
- Files Changed: {files_changed}
- Action: {action}

**Changed Files:** {files_summary}

Your task:
1. Provide a 2-3 sentence summary of what changed
2. List 3-5 key changes
3. Assess impact level (Low/Medium/High)
4. Suggest 3-5 improvements or best practices
5. Identify improvement areas
6. List recommended actions with descriptions

Format your response as JSON with these exact keys:
- key_changes: array of strings
- summary: string
- impact_level: string (Low/Medium/High)
- suggestions: array of strings
- improvement_areas: array of strings
- recommended_actions: array of objects with action and description

Be specific and actionable. Focus on code quality, testing, documentation, and best practices.
""")
        
        # Get files summary
        files_data = summary.get("files", [])
        files_summary = self._summarize_files(files_data)
        
        # Run analysis
        prompt_text = analysis_prompt.format(
            pr_number=pr_number,
            pr_title=pr_title,
            repo=repo,
            files_changed=files_changed,
            action=summary.get("action", "unknown"),
            files_summary=files_summary,
        )
        
        try:
            content = await self.llm.invoke(prompt_text)
            
            # Extract JSON from response
            try:
                import re
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    data = json.loads(json_match.group())
                else:
                    data = json.loads(content)
            except:
                data = self._parse_fallback_response(content)
            
            return PRAnalysisResult(
                pr_number=pr_number,
                pr_title=pr_title,
                files_changed=files_changed,
                summary=data.get("summary", "No summary available"),
                key_changes=data.get("key_changes", []),
                impact_level=data.get("impact_level", "Medium"),
                suggestions=data.get("suggestions", []),
                improvement_areas=data.get("improvement_areas", []),
                recommended_actions=data.get("recommended_actions", []),
                timestamp=pr_data.get("timestamp", datetime.now().isoformat())
            )
            
        except Exception as e:
            print(f"Error analyzing PR {pr_number}: {e}")
            return None
    
    def _summarize_files(self, files: List[Dict]) -> str:
        """Create a summary of changed files"""
        if not files:
            return "No files changed"
        
        file_stats = {"M": 0, "A": 0, "D": 0, "R": 0}
        for f in files:
            status = f.get("status", "?")
            file_stats[status] = file_stats.get(status, 0) + 1
        
        summary_parts = []
        if file_stats["A"] > 0:
            summary_parts.append(f"{file_stats['A']} added")
        if file_stats["M"] > 0:
            summary_parts.append(f"{file_stats['M']} modified")
        if file_stats["D"] > 0:
            summary_parts.append(f"{file_stats['D']} deleted")
        if file_stats["R"] > 0:
            summary_parts.append(f"{file_stats['R']} renamed")
        
        return ", ".join(summary_parts)
    
    def _parse_fallback_response(self, content: str) -> Dict:
        """Fallback parser if JSON extraction fails"""
        return {
            "summary": content[:200],
            "key_changes": [],
            "impact_level": "Medium",
            "suggestions": [],
            "improvement_areas": [],
            "recommended_actions": []
        }


async def analyze_all_events(events_file: str = "repo-monitor-events.jsonl", 
                            provider: str = "openai",
                            filter_type: str = "pull_request") -> List[PRAnalysisResult]:
    """
    Analyze all events from the JSONL file
    
    Args:
        events_file: Path to events JSONL file
        provider: LLM provider (openai or anthropic)
        filter_type: Only analyze events of this type
    
    Returns:
        List of PRAnalysisResult objects
    """
    
    if not os.path.exists(events_file):
        print(f"❌ Events file not found: {events_file}")
        return []
    
    engine = PRIntelligenceEngine(provider=provider)
    results = []
    
    print(f"\n🔍 Analyzing PR events from {events_file}...\n")
    
    with open(events_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            try:
                event = json.loads(line.strip())
                
                if event.get("event_name") != filter_type:
                    continue
                
                print(f"📊 Analyzing Event {line_num}...", end=" ")
                result = await engine.analyze_pr_event(event)
                
                if result:
                    results.append(result)
                    print(f"✓ PR #{result.pr_number}")
                else:
                    print("⊘ Skipped")
                    
            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(f"✗ Error: {e}")
    
    return results


def save_analysis_results(results: List[PRAnalysisResult], 
                         output_file: str = "pr-analysis-results.jsonl"):
    """Save analysis results to a file"""
    
    with open(output_file, 'w') as f:
        for result in results:
            f.write(json.dumps({
                "pr_number": result.pr_number,
                "pr_title": result.pr_title,
                "files_changed": result.files_changed,
                "summary": result.summary,
                "key_changes": result.key_changes,
                "impact_level": result.impact_level,
                "suggestions": result.suggestions,
                "improvement_areas": result.improvement_areas,
                "recommended_actions": result.recommended_actions,
                "timestamp": result.timestamp
            }, ensure_ascii=False) + "\n")
    
    print(f"✅ Saved {len(results)} analysis results to {output_file}")


def display_analysis_report(results: List[PRAnalysisResult]):
    """Display a formatted analysis report"""
    
    if not results:
        print("No analysis results to display")
        return
    
    print("\n" + "="*80)
    print("📋 PR INTELLIGENCE REPORT")
    print("="*80 + "\n")
    
    for result in results:
        print(f"PR #{result.pr_number}: {result.pr_title}")
        print("-" * 80)
        print(f"📊 Impact Level: {result.impact_level}")
        print(f"📁 Files Changed: {result.files_changed}")
        print(f"\n📝 Summary:\n{result.summary}")
        
        if result.key_changes:
            print(f"\n🔑 Key Changes:")
            for change in result.key_changes:
                print(f"  • {change}")
        
        if result.suggestions:
            print(f"\n💡 Suggestions for Improvement:")
            for i, suggestion in enumerate(result.suggestions, 1):
                print(f"  {i}. {suggestion}")
        
        if result.improvement_areas:
            print(f"\n⚠️  Areas for Improvement:")
            for area in result.improvement_areas:
                print(f"  • {area}")
        
        if result.recommended_actions:
            print(f"\n✅ Recommended Actions:")
            for action in result.recommended_actions:
                if isinstance(action, dict):
                    print(f"  • {action.get('action', 'Unknown')}")
                    print(f"    → {action.get('description', '')}")
        
        print("\n" + "="*80 + "\n")


async def interactive_review_and_apply(results: List[PRAnalysisResult]):
    """
    Interactive mode to review suggestions and apply changes
    """
    
    if not results:
        print("No analysis results to review")
        return
    
    print("\n" + "🎯 INTERACTIVE REVIEW MODE" + "\n")
    
    approved_actions = []
    
    for i, result in enumerate(results, 1):
        print(f"\n[{i}/{len(results)}] PR #{result.pr_number}: {result.pr_title}")
        print("-" * 80)
        
        if result.summary:
            print(f"📝 Summary: {result.summary}")
        
        if result.suggestions:
            print(f"\n💡 Suggestions:")
            for j, suggestion in enumerate(result.suggestions, 1):
                print(f"  {j}. {suggestion}")
        
        # Ask for permission
        print("\n" + "—" * 40)
        
        while True:
            user_input = input(
                "\n Do you want to apply suggested changes? (y/n/s/q)\n"
                "  y = Yes, apply all suggestions\n"
                "  n = No, skip this PR\n"
                "  s = Show recommended actions\n"
                "  q = Quit\n"
                "→ "
            ).lower().strip()
            
            if user_input == "y":
                approved_actions.append({
                    "pr_number": result.pr_number,
                    "pr_title": result.pr_title,
                    "actions": result.recommended_actions,
                    "suggestions": result.suggestions
                })
                print("✅ Approved")
                break
            elif user_input == "n":
                print("⊘ Skipped")
                break
            elif user_input == "s":
                if result.recommended_actions:
                    print("\n📋 Recommended Actions:")
                    for action in result.recommended_actions:
                        if isinstance(action, dict):
                            print(f"  • {action.get('action', 'Unknown')}")
                            print(f"    → {action.get('description', '')}")
                else:
                    print("No specific actions recommended")
            elif user_input == "q":
                return approved_actions
            else:
                print("Invalid input, please try again")
    
    return approved_actions


# Example usage
if __name__ == "__main__":
    import sys
    
    async def main():
        provider = os.getenv("LLM_PROVIDER", "openai")
        
        # Analyze all events
        results = await analyze_all_events(provider=provider)
        
        if results:
            # Display report
            display_analysis_report(results)
            
            # Save results
            save_analysis_results(results)
            
            # Interactive review
            print("\n🚀 Starting interactive review...")
            approved = await interactive_review_and_apply(results)
            
            if approved:
                print(f"\n✅ {len(approved)} PRs approved for changes")
                for approval in approved:
                    print(f"  • PR #{approval['pr_number']}: {approval['pr_title']}")
    
    asyncio.run(main())
