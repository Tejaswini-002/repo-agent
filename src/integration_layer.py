#!/usr/bin/env python3
"""
Unified Integration Layer
Connects: PR Intelligence Engine + RAG System + Dashboard
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, TYPE_CHECKING
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
import os

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.pr_intelligence import PRAnalysisResult as PRAnalysisResultType
else:
    PRAnalysisResultType = Any

# Import PR Intelligence Engine
try:
    from src.pr_intelligence import PRIntelligenceEngine
except ImportError:
    try:
        from pr_intelligence import PRIntelligenceEngine
    except ImportError:
        PRIntelligenceEngine = None

# Import RAG components
try:
    from langchain_community.vectorstores import Chroma
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_core.documents import Document
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logger.warning("Chroma not available - RAG features disabled")


@dataclass
class IntegratedPRAnalysis:
    """Complete PR analysis with RAG context"""
    pr_number: int
    pr_title: str
    summary: str
    key_changes: List[str]
    impact_level: str
    suggestions: List[str]
    recommended_actions: List[Dict[str, str]]
    rag_context: List[Dict[str, Any]]  # Similar PRs from vector store
    confidence_score: float
    timestamp: str


class RAGSystem:
    """Vector database for PR analysis results"""
    
    def __init__(self, persist_dir: str = "./data/chroma_db"):
        self.persist_dir = persist_dir
        self.initialized = False
        
        if not CHROMA_AVAILABLE:
            logger.warning("RAG System requires Chroma - features disabled")
            return
            
        try:
            self.embeddings = HuggingFaceEmbeddings(
                model_name="all-MiniLM-L6-v2"
            )
            self.vectorstore = Chroma(
                collection_name="pr_analyses",
                embedding_function=self.embeddings,
                persist_directory=persist_dir
            )
            self.initialized = True
            logger.info(f"RAG System initialized with {persist_dir}")
        except Exception as e:
            logger.error(f"Failed to initialize RAG: {e}")
    
    async def add_analysis(self, analysis: PRAnalysisResultType):
        """Add PR analysis to vector store"""
        if not self.initialized:
            return
        
        try:
            # Create searchable document
            content = f"""
PR #{analysis.pr_number}: {analysis.pr_title}

Summary: {analysis.summary}

Key Changes:
{chr(10).join(f"- {change}" for change in analysis.key_changes)}

Suggestions:
{chr(10).join(f"- {sug}" for sug in analysis.suggestions)}

Impact Level: {analysis.impact_level}
"""
            
            doc = Document(
                page_content=content,
                metadata={
                    "pr_number": analysis.pr_number,
                    "pr_title": analysis.pr_title,
                    "impact_level": analysis.impact_level,
                    "timestamp": analysis.timestamp
                }
            )
            
            self.vectorstore.add_documents([doc])
            logger.info(f"Added PR #{analysis.pr_number} to vector store")
        except Exception as e:
            logger.error(f"Failed to add analysis to RAG: {e}")
    
    async def find_similar_prs(self, 
                               query: str, 
                               k: int = 3) -> List[Dict[str, Any]]:
        """Find similar PRs using vector similarity"""
        if not self.initialized:
            return []
        
        try:
            results = self.vectorstore.similarity_search_with_score(query, k=k)
            
            similar = []
            for doc, score in results:
                similar.append({
                    "pr_number": doc.metadata.get("pr_number"),
                    "pr_title": doc.metadata.get("pr_title"),
                    "similarity_score": float(score),
                    "content": doc.page_content[:200]
                })
            
            return similar
        except Exception as e:
            logger.error(f"RAG search failed: {e}")
            return []
    
    async def get_improvement_patterns(self) -> Dict[str, Any]:
        """Analyze patterns in stored PRs for insights"""
        if not self.initialized:
            return {}
        
        try:
            # Get all documents
            results = self.vectorstore.get()
            
            impact_counts = {}
            suggestion_freq = {}
            
            for metadata in results.get("metadatas", []):
                impact = metadata.get("impact_level", "Unknown")
                impact_counts[impact] = impact_counts.get(impact, 0) + 1
            
            return {
                "total_analyzed": len(results.get("metadatas", [])),
                "impact_distribution": impact_counts,
                "most_recent": results.get("metadatas", [])[-1] if results.get("metadatas") else None
            }
        except Exception as e:
            logger.error(f"Pattern analysis failed: {e}")
            return {}


class IntegrationLayer:
    """Unified layer connecting all components"""
    
    def __init__(self, 
                 llm_model: str = "llama3",
                 enable_rag: bool = True,
                 github_token: Optional[str] = None):
        self.llm_model = llm_model
        self.events_file = "repo-monitor-events.jsonl"
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        
        # Initialize PR Intelligence Engine
        self.pr_engine = None
        if PRIntelligenceEngine:
            try:
                self.pr_engine = PRIntelligenceEngine(
                    model=llm_model,
                    github_token=self.github_token
                )
                provider = os.getenv("LLM_PROVIDER", "ollama")
                logger.info(f"PR Intelligence Engine initialized with {provider} ({llm_model})")
            except Exception as e:
                logger.error(f"Failed to initialize PR Engine: {e}")
        
        # Initialize RAG System
        self.rag = RAGSystem() if enable_rag else None
        
        # Callbacks for real-time updates
        self.callbacks: List[callable] = []
    
    def subscribe(self, callback: callable):
        """Subscribe to analysis updates"""
        self.callbacks.append(callback)
    
    async def _notify(self, data: Dict[str, Any]):
        """Notify all subscribers"""
        for callback in self.callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                logger.error(f"Callback error: {e}")
    
    async def analyze_pr_with_github(self, repo: str, pr_number: int) -> Optional[IntegratedPRAnalysis]:
        """
        Analyze PR by fetching actual code from GitHub
        This provides deep code-level analysis with diffs
        """
        if not self.pr_engine:
            logger.error("PR Engine not initialized")
            return None
        
        try:
            # Notify: Analysis started
            await self._notify({
                "type": "analysis_started",
                "pr_number": pr_number,
                "repo": repo
            })
            
            # Step 1: Fetch and analyze PR with actual code
            analysis = await self.pr_engine.analyze_pr_with_code(repo, pr_number)
            
            # Notify: Analysis complete
            await self._notify({
                "type": "analysis_complete",
                "data": asdict(analysis)
            })
            
            # Step 2: Add to RAG for future reference
            if self.rag:
                await self.rag.add_analysis(analysis)
            
            # Step 3: Find similar PRs from history
            rag_context = []
            if self.rag:
                rag_context = await self.rag.find_similar_prs(analysis.summary, k=3)
            
            # Calculate confidence based on RAG context
            confidence = 0.95 if len(rag_context) > 0 else 0.85
            
            # Step 4: Create integrated result
            result = IntegratedPRAnalysis(
                pr_number=analysis.pr_number,
                pr_title=analysis.pr_title,
                summary=analysis.summary,
                key_changes=analysis.key_changes,
                impact_level=analysis.impact_level,
                suggestions=analysis.suggestions,
                recommended_actions=analysis.recommended_actions,
                rag_context=rag_context,
                confidence_score=confidence,
                timestamp=datetime.utcnow().isoformat()
            )
            
            # Notify: Integration complete
            await self._notify({
                "type": "integration_complete",
                "result": asdict(result)
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            await self._notify({
                "type": "analysis_failed",
                "error": str(e)
            })
            return None
    
    async def analyze_pr_event(self, event: Dict[str, Any]) -> Optional[IntegratedPRAnalysis]:
        """Analyze PR with full integration (event-based, limited data)"""
        if not self.pr_engine:
            logger.error("PR Engine not initialized")
            return None
        
        try:
            # Notify: Analysis started
            await self._notify({
                "type": "analysis_started",
                "pr_number": event.get("summary", {}).get("pr_number")
            })
            
            # Step 1: Analyze PR with LLM
            analysis = await self.pr_engine.analyze_pr_event(event)
            
            # Notify: Analysis complete
            await self._notify({
                "type": "analysis_complete",
                "data": asdict(analysis)
            })
            
            # Step 2: Add to RAG for future reference
            if self.rag:
                await self.rag.add_analysis(analysis)
            
            # Step 3: Find similar PRs from history
            rag_context = []
            if self.rag:
                rag_context = await self.rag.find_similar_prs(analysis.summary, k=3)
            
            # Calculate confidence based on RAG context
            confidence = 0.95 if len(rag_context) > 0 else 0.80
            
            # Step 4: Create integrated result
            result = IntegratedPRAnalysis(
                pr_number=analysis.pr_number,
                pr_title=analysis.pr_title,
                summary=analysis.summary,
                key_changes=analysis.key_changes,
                impact_level=analysis.impact_level,
                suggestions=analysis.suggestions,
                recommended_actions=analysis.recommended_actions,
                rag_context=rag_context,
                confidence_score=confidence,
                timestamp=datetime.utcnow().isoformat()
            )
            
            # Notify: Final result
            await self._notify({
                "type": "analysis_result",
                "data": asdict(result)
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            await self._notify({
                "type": "analysis_error",
                "error": str(e)
            })
            return None
    
    async def analyze_all_events(self) -> List[IntegratedPRAnalysis]:
        """Analyze all stored events"""
        results = []
        
        if not Path(self.events_file).exists():
            logger.warning(f"Events file not found: {self.events_file}")
            return results
        
        try:
            with open(self.events_file, "r") as f:
                for line in f:
                    if not line.strip():
                        continue
                    
                    event = json.loads(line)
                    
                    # Only analyze PR events
                    if event.get("event_name") != "pull_request":
                        continue
                    
                    result = await self.analyze_pr_event(event)
                    if result:
                        results.append(result)
                    
                    # Small delay to avoid rate limiting
                    await asyncio.sleep(0.5)
        
        except Exception as e:
            logger.error(f"Batch analysis failed: {e}")
        
        return results
    
    async def get_insights(self) -> Dict[str, Any]:
        """Get overall insights from RAG system"""
        if not self.rag:
            return {}
        
        return await self.rag.get_improvement_patterns()
    
    def save_analysis(self, analysis: IntegratedPRAnalysis, 
                      output_file: str = "pr-analysis-integrated.jsonl"):
        """Save analysis to file"""
        try:
            with open(output_file, "a") as f:
                f.write(json.dumps(asdict(analysis), default=str) + "\n")
            logger.info(f"Saved analysis to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save analysis: {e}")


async def demo():
    """Demo of integration layer"""
    # Initialize
    integration = IntegrationLayer(
        llm_provider="anthropic",
        enable_rag=True
    )
    
    # Subscribe to updates
    async def print_update(data):
        print(f"[UPDATE] {data['type']}")
    
    integration.subscribe(print_update)
    
    # Analyze all events
    results = await integration.analyze_all_events()
    
    print(f"\nAnalyzed {len(results)} PRs")
    
    # Get insights
    insights = await integration.get_insights()
    print(f"\nInsights: {json.dumps(insights, indent=2)}")
    
    # Save results
    for result in results:
        integration.save_analysis(result)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(demo())
