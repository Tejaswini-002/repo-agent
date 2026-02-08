"""Streamlit web application with PR Intelligence Integration"""

import sys
import os
from pathlib import Path

import streamlit as st
from typing import Dict, Any, List
import asyncio
import logging
from datetime import datetime
import json

# Ensure project root is on sys.path for local imports
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import integration layer
try:
    from src.integration_layer import IntegrationLayer
    from src.pr_intelligence import PRAnalysisResult
except ImportError:
    st.error("Required modules not found. Install dependencies: pip install -r requirements.txt")
    st.stop()


# ============ Page Configuration ============

st.set_page_config(
    page_title="Repo Monitor Agent - PR Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🤖 Repo Monitor Agent - PR Intelligence")
st.markdown("""
**AI-powered PR analysis with RAG context awareness**
- Intelligent summaries of code changes
- Smart improvement suggestions
- Similar PR discovery from history
- Confidence-based recommendations
""")

# ============ Sidebar Configuration ============

with st.sidebar:
    st.header("⚙️ Configuration")

    llm_provider = st.selectbox(
        "LLM Provider",
        ["foundry_local", "ollama"],
        index=0 if os.getenv("LLM_PROVIDER", "foundry_local").lower() == "foundry_local" else 1,
        help="Use Foundry Local or Ollama"
    )

    os.environ["LLM_PROVIDER"] = llm_provider

    if llm_provider == "foundry_local":
        st.info("💡 Using **Foundry Local** (OpenAI-compatible endpoint).")
        foundry_model = st.text_input(
            "Foundry Local Model",
            value=os.getenv("FOUNDRY_LOCAL_MODEL", ""),
            help="Model name served by Foundry Local"
        )
        foundry_base_url = st.text_input(
            "Foundry Local Base URL",
            value=os.getenv("FOUNDRY_LOCAL_BASE_URL", "http://localhost:8000"),
            help="Example: http://localhost:8000"
        )
        if foundry_model:
            os.environ["FOUNDRY_LOCAL_MODEL"] = foundry_model
        if foundry_base_url:
            os.environ["FOUNDRY_LOCAL_BASE_URL"] = foundry_base_url
        provider = foundry_model or "llama3"
    else:
        st.success("💡 Using **Ollama** - Free & Open Source!\n\nNo API keys needed. Runs locally.")
        provider = st.selectbox(
            "Ollama Model",
            ["llama3", "mistral", "codellama", "llama2", "phi", "gemma"],
            help="Choose from installed Ollama models. Install: ollama pull <model>"
        )
    
    # RAG Settings
    enable_rag = st.checkbox("Enable RAG Context", value=True)
    
    st.divider()
    
    st.header("📊 Quick Stats")
    try:
        integration = IntegrationLayer(
            llm_model=provider,
            enable_rag=enable_rag
        )
        insights = asyncio.run(integration.get_insights())
        
        if insights:
            st.metric("Total Analyzed", insights.get("total_analyzed", 0))
    except:
        pass


# ============ Main Content Tabs ============

tab1, tab2, tab3, tab4 = st.tabs(
    ["🔍 Analyze PR", "📚 Batch Analysis", "💡 Insights", "📊 History"]
)


# ============ Tab 1: Single PR Analysis ============

with tab1:
    st.header("🔍 Deep PR Code Analysis")
    st.info("💡 **New!** Agent now fetches actual code changes from GitHub for comprehensive analysis")
    
    col1, col2 = st.columns(2)
    
    with col1:
        pr_number = st.number_input("PR Number", min_value=1, value=1)
        repo = st.text_input("Repository", value="Tejaswini-002/repo-agent")
    
    with col2:
        github_token = st.text_input(
            "GitHub Token (Optional)", 
            type="password",
            help="For private repos or higher rate limits. Get token at: https://github.com/settings/tokens"
        )
        analysis_mode = st.selectbox(
            "Analysis Mode",
            ["Deep Code Analysis (Recommended)", "Quick Summary"],
            help="Deep mode fetches actual code changes. Quick mode uses PR metadata only."
        )
    
    if st.button("🚀 Analyze PR", use_container_width=True):
        use_deep_analysis = "Deep" in analysis_mode
        
        with st.spinner(f"{'Fetching code and analyzing' if use_deep_analysis else 'Analyzing'} PR #{pr_number}..."):
            try:
                integration = IntegrationLayer(
                    llm_model=provider,
                    enable_rag=enable_rag,
                    github_token=github_token if github_token else None
                )
                
                if use_deep_analysis:
                    # Use new deep analysis with actual code
                    result = asyncio.run(integration.analyze_pr_with_github(repo, pr_number))
                else:
                    # Fallback to event-based analysis
                    event = {
                        "event_name": "pull_request",
                        "summary": {
                            "pr_number": pr_number,
                            "title": f"PR #{pr_number}",
                            "changed_files_count": 0,
                            "repo": repo
                        }
                    }
                    result = asyncio.run(integration.analyze_pr_event(event))
                
                if result:
                    st.success("✅ Analysis Complete" + (" (with code diff)" if use_deep_analysis else ""))
                    
                    # Display Results
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Impact Level", result.impact_level)
                    with col2:
                        st.metric("Confidence", f"{result.confidence_score:.1%}")
                    with col3:
                        st.metric("Suggestions", len(result.suggestions))
                    
                    st.divider()
                    
                    # Summary
                    st.subheader("📝 Summary")
                    st.write(result.summary)
                    
                    # Key Changes
                    st.subheader("🔑 Key Changes")
                    for change in result.key_changes:
                        st.write(f"• {change}")
                    
                    # Suggestions
                    st.subheader("💡 Improvement Suggestions")
                    for i, suggestion in enumerate(result.suggestions, 1):
                        st.write(f"{i}. {suggestion}")
                    
                    # Recommended Actions
                    st.subheader("✅ Recommended Actions")
                    for action in result.recommended_actions:
                        with st.expander(action.get("action", "Action")):
                            st.write(action.get("description", ""))
                    
                    # RAG Context
                    if result.rag_context:
                        st.subheader("🔗 Similar PRs from History")
                        for similar in result.rag_context:
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.write(f"**PR #{similar['pr_number']}**: {similar['pr_title']}")
                                st.caption(similar['content'][:100] + "...")
                            with col2:
                                st.metric("Match", f"{similar['similarity_score']:.1%}")
                    
                    # Export
                    st.divider()
                    if st.button("💾 Save Analysis"):
                        integration.save_analysis(result)
                        st.success("Analysis saved to pr-analysis-integrated.jsonl")
                else:
                    st.error("Analysis failed")
            except Exception as e:
                st.error(f"Error: {str(e)}")
                logger.error(f"Analysis error: {e}")


# ============ Tab 2: Batch Analysis ============

with tab2:
    st.header("Batch PR Analysis")
    st.write("Analyze all stored PR events at once")
    
    progress_container = st.container()
    results_container = st.container()
    
    if st.button("🚀 Start Batch Analysis", use_container_width=True):
        try:
            integration = IntegrationLayer(
                llm_model=provider,
                enable_rag=enable_rag
            )
            
            # Progress tracking
            progress_bar = progress_container.progress(0)
            status_text = progress_container.empty()
            
            # Run analysis
            status_text.info("Starting batch analysis...")
            results = asyncio.run(integration.analyze_all_events())
            
            progress_bar.progress(100)
            status_text.success(f"✅ Completed! Analyzed {len(results)} PRs")
            
            # Display results
            with results_container:
                if results:
                    st.subheader(f"📊 Analysis Results ({len(results)} PRs)")
                    
                    # Summary metrics
                    col1, col2, col3, col4 = st.columns(4)
                    
                    impact_counts = {}
                    total_suggestions = 0
                    avg_confidence = 0
                    
                    for r in results:
                        impact_counts[r.impact_level] = impact_counts.get(r.impact_level, 0) + 1
                        total_suggestions += len(r.suggestions)
                        avg_confidence += r.confidence_score
                    
                    with col1:
                        st.metric("PRs Analyzed", len(results))
                    with col2:
                        st.metric("Total Suggestions", total_suggestions)
                    with col3:
                        st.metric("Avg Confidence", f"{avg_confidence/len(results):.1%}")
                    with col4:
                        high_impact = impact_counts.get("High", 0)
                        st.metric("High Impact", high_impact)
                    
                    st.divider()
                    
                    # Results table
                    st.subheader("PR Summaries")
                    
                    for result in results:
                        with st.expander(
                            f"PR #{result.pr_number}: {result.pr_title} - {result.impact_level}",
                            expanded=False
                        ):
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.write(f"**Impact**: {result.impact_level}")
                            with col2:
                                st.write(f"**Confidence**: {result.confidence_score:.1%}")
                            with col3:
                                st.write(f"**Suggestions**: {len(result.suggestions)}")
                            
                            st.write(result.summary)
                            
                            # Save individual
                            if st.button(f"Save PR #{result.pr_number}", key=f"save_{result.pr_number}"):
                                integration.save_analysis(result)
                                st.success("Saved!")
                else:
                    st.info("No PR events found in repo-monitor-events.jsonl")
        except Exception as e:
            st.error(f"Batch analysis error: {str(e)}")
            logger.error(f"Batch error: {e}")


# ============ Tab 3: Insights ============

with tab3:
    st.header("📈 RAG-Based Insights")
    st.write("Learn from patterns in your PR history")
    
    if st.button("🔄 Generate Insights", use_container_width=True):
        try:
            integration = IntegrationLayer(
                llm_model=provider,
                enable_rag=enable_rag
            )
            
            with st.spinner("Analyzing patterns..."):
                insights = asyncio.run(integration.get_insights())
            
            if insights:
                st.success("✅ Insights Generated")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.metric("Total PRs Analyzed", insights.get("total_analyzed", 0))
                
                with col2:
                    most_recent = insights.get("most_recent")
                    if most_recent:
                        st.write("📅 Most Recent PR")
                        st.caption(most_recent.get("pr_title", "N/A"))
                
                st.divider()
                
                # Impact distribution
                st.subheader("Impact Distribution")
                impact_dist = insights.get("impact_distribution", {})
                if impact_dist:
                    st.bar_chart(impact_dist)
                else:
                    st.info("No data available yet")
                
                # Raw data
                st.subheader("Raw Insights")
                st.json(insights)
            else:
                st.info("No insights available. Run batch analysis first.")
        except Exception as e:
            st.error(f"Insights error: {str(e)}")


# ============ Tab 4: History ============

with tab4:
    st.header("📚 Analysis History")
    
    try:
        import pathlib
        
        # Check if results file exists
        results_file = pathlib.Path("pr-analysis-integrated.jsonl")
        
        if results_file.exists():
            analyses = []
            with open(results_file) as f:
                for line in f:
                    if line.strip():
                        analyses.append(json.loads(line))
            
            st.metric("Saved Analyses", len(analyses))
            
            if analyses:
                st.subheader("Recent Analyses")
                for analysis in reversed(analyses[-10:]):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"**PR #{analysis['pr_number']}**: {analysis['pr_title']}")
                        st.caption(analysis['summary'][:100] + "...")
                    with col2:
                        st.write(f"Impact: {analysis['impact_level']}")
        else:
            st.info("No analysis history yet. Run some analyses first!")
    except Exception as e:
        st.error(f"Error loading history: {str(e)}")


# ============ Footer ============

st.divider()
st.caption(f"Repo Monitor Agent v2.0 | Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
