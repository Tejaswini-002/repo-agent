#!/usr/bin/env python3
"""
Enhanced Flask Server with PR Intelligence Integration
Webhook receiver + integrated analysis
"""

from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask, request, Response, jsonify, render_template_string
import hmac
import hashlib
import os
import json
import threading
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional, TYPE_CHECKING
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if TYPE_CHECKING:
    from src.integration_layer import IntegrationLayer as IntegrationLayerType
    from src.pr_review_service import PRReviewService as PRReviewServiceType
else:
    IntegrationLayerType = Any
    PRReviewServiceType = Any

# Import integration layer
try:
    from src.integration_layer import IntegrationLayer
except ImportError:
    logger.warning("Integration layer not available")
    IntegrationLayer = None

# Import PR review service
try:
    from src.pr_review_service import PRReviewService
except ImportError:
    logger.warning("PR review service not available")
    PRReviewService = None

# Import push analysis service
try:
    from src.push_analysis import PushAnalysisService
except ImportError:
    logger.warning("Push analysis service not available")
    PushAnalysisService = None

app = Flask(__name__)

# In-memory store of recent events (capped)
EVENTS_LOCK = threading.Lock()
RECENT_EVENTS: List[dict] = []
ANALYSIS_RESULTS: List[dict] = []
MAX_EVENTS = 200

# Integration layer
integration_layer = None
review_service = None
push_analysis_service = None
LAST_PUSH_ANALYSIS: Dict[str, Any] = {}

UI_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Repo Monitor — Change Summary</title>
        <style>
            :root { color-scheme: dark; }
            body {
                margin: 0;
                font-family: Inter, system-ui, -apple-system, Segoe UI, Arial, sans-serif;
                background: radial-gradient(1200px 600px at 10% 0%, #151b2b 0%, #0f1115 55%);
                color: #e7e9ee;
            }
            .container { max-width: 1100px; margin: 48px auto; padding: 0 24px; }
            .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
            .title { font-size: 28px; font-weight: 700; }
            .subtitle { color: #9aa4b2; font-size: 14px; }
            .card {
                background: #151922;
                border: 1px solid #242a38;
                border-radius: 16px;
                padding: 24px;
                box-shadow: 0 16px 40px rgba(0,0,0,0.35);
            }
            h2 { margin: 18px 0 10px; font-size: 18px; color: #cdd4f6; }
            .summary { font-size: 15px; line-height: 1.7; color: #d6d9e0; }
            .badges { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
            .badge {
                padding: 6px 10px;
                border-radius: 999px;
                background: #1a2130;
                border: 1px solid #2a3550;
                color: #b9c2ff;
                font-size: 12px;
            }
            .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-top: 14px; }
            .stat {
                background: #101521;
                border: 1px solid #242a38;
                border-radius: 12px;
                padding: 10px 12px;
                font-size: 13px;
            }
            table { width: 100%; border-collapse: collapse; margin-top: 12px; }
            th, td { text-align: left; padding: 12px; border-bottom: 1px solid #242a38; vertical-align: top; }
            th { color: #aeb6c8; font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; }
            td { font-size: 14px; color: #d7dce6; }
            code { background: #0f1420; padding: 2px 6px; border-radius: 6px; color: #c6d1ff; }
            .empty {
                color: #9aa4b2;
                font-style: italic;
                background: #0f1420;
                border: 1px dashed #2a3550;
                padding: 16px;
                border-radius: 12px;
            }
            .footer { margin-top: 14px; color: #8d97a6; font-size: 12px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div>
                    <div class="title">Summary</div>
                    <div class="subtitle">Latest push analysis</div>
                </div>
            </div>
            <div class="card">
                {% if summary %}
                    <div class="summary">{{ summary }}</div>
                    <div class="badges">
                        <span class="badge">Impact: {{ impact }}</span>
                        <span class="badge">Files: {{ stats.files }}</span>
                        <span class="badge">Additions: {{ stats.additions }}</span>
                        <span class="badge">Deletions: {{ stats.deletions }}</span>
                    </div>
                    <div class="stats">
                        <div class="stat">Summary generated from push diff</div>
                        <div class="stat">Includes file list + key changes</div>
                    </div>
                    <h2>Files Changed</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>File</th>
                                <th>Summary</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for item in files %}
                                <tr>
                                    <td><code>{{ item.path }}</code></td>
                                    <td>{{ item.summary }}</td>
                                </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                    <div class="footer">Tip: Push new commits to refresh this view.</div>
                {% else %}
                    <div class="empty">No analysis yet. Send a push event to /webhook to populate this view.</div>
                {% endif %}
            </div>
        </div>
    </body>
</html>
"""


def get_integration_layer() -> Optional[IntegrationLayerType]:
    """Get or create integration layer"""
    global integration_layer
    if integration_layer is None and IntegrationLayer:
        try:
            llm_model = (
                os.getenv("LLM_MODEL")
                or os.getenv("FOUNDRY_LOCAL_MODEL")
                or "llama3"
            )
            enable_rag = os.getenv("ENABLE_RAG", "0") == "1"
            integration_layer = IntegrationLayer(
                llm_model=llm_model,
                enable_rag=enable_rag
            )
            logger.info("Integration layer initialized")
        except Exception as e:
            logger.error(f"Failed to initialize integration layer: {e}")
    return integration_layer


def get_review_service() -> Optional[PRReviewServiceType]:
    """Get or create PR review service"""
    global review_service
    if review_service is None and PRReviewService:
        try:
            review_service = PRReviewService(
                light_model=os.getenv("REVIEW_LIGHT_MODEL", "llama3"),
                heavy_model=os.getenv("REVIEW_HEAVY_MODEL", "llama3"),
                github_token=os.getenv("GITHUB_TOKEN"),
                review_simple_changes=os.getenv("REVIEW_SIMPLE_CHANGES", "0") == "1",
                simple_change_threshold=int(os.getenv("REVIEW_SIMPLE_THRESHOLD", "20")),
            )
            logger.info("PR review service initialized")
        except Exception as e:
            logger.error(f"Failed to initialize PR review service: {e}")
    return review_service


def get_push_analysis_service() -> Optional[PushAnalysisService]:
    """Get or create push analysis service"""
    global push_analysis_service
    if push_analysis_service is None and PushAnalysisService:
        try:
            llm_model = (
                os.getenv("LLM_MODEL")
                or os.getenv("FOUNDRY_LOCAL_MODEL")
                or "llama3"
            )
            push_analysis_service = PushAnalysisService(
                model=llm_model,
                github_token=os.getenv("GITHUB_TOKEN"),
            )
            logger.info("Push analysis service initialized")
        except Exception as e:
            logger.error(f"Failed to initialize push analysis service: {e}")
    return push_analysis_service


# ============ Webhook Signature Verification ============

def verify_signature(secret: str, payload: bytes, signature_header: str) -> bool:
    """Verify GitHub webhook signature"""
    if not signature_header:
        return False
    parts = signature_header.split("=", 1)
    if len(parts) != 2:
        return False
    sha_name, signature = parts
    if sha_name != "sha256":
        return False
    mac = hmac.new(secret.encode(), msg=payload, digestmod=hashlib.sha256)
    expected = mac.hexdigest()
    return hmac.compare_digest(expected, signature)


def push_event(ev: dict):
    """Store event in memory and disk"""
    ev["timestamp"] = datetime.utcnow().isoformat() + "Z"
    with EVENTS_LOCK:
        RECENT_EVENTS.append(ev)
        if len(RECENT_EVENTS) > MAX_EVENTS:
            RECENT_EVENTS.pop(0)
    
    # Optionally append to disk if configured
    path = os.getenv("MONITOR_EVENTS_PATH", "").strip()
    if path:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Failed to write to disk: {e}")


async def analyze_event_async(event: dict):
    """Analyze event asynchronously with integration layer"""
    try:
        integration = get_integration_layer()
        if not integration:
            logger.warning("Integration layer not available")
            return
        
        result = await integration.analyze_pr_event(event)
        if result:
            with EVENTS_LOCK:
                ANALYSIS_RESULTS.append({
                    "pr_number": result.pr_number,
                    "pr_title": result.pr_title,
                    "summary": result.summary,
                    "key_changes": result.key_changes,
                    "impact_level": result.impact_level,
                    "suggestions": result.suggestions,
                    "confidence_score": result.confidence_score,
                    "timestamp": result.timestamp
                })
            logger.info(f"Analyzed PR #{result.pr_number}")
    except Exception as e:
        logger.error(f"Analysis error: {e}")


def analyze_event_background(event: dict):
    """Run analysis in background thread"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(analyze_event_async(event))
    except Exception as e:
        logger.error(f"Background analysis error: {e}")


def review_pr_background(repo: str, pr_number: int):
    """Run PR review in background thread"""
    try:
        service = get_review_service()
        if not service:
            logger.warning("Review service not available")
            return
        asyncio.run(service.post_review(repo, pr_number))
    except Exception as e:
        logger.error(f"Background review error: {e}")


def reply_review_comment_background(event: dict):
    """Reply to review comment in background thread"""
    try:
        service = get_review_service()
        if not service:
            logger.warning("Review service not available")
            return
        asyncio.run(service.handle_review_comment_event(event))
    except Exception as e:
        logger.error(f"Background reply error: {e}")


def analyze_push_background(repo: str, before: str, after: str, commits: List[dict]):
    """Analyze push event in background"""
    global LAST_PUSH_ANALYSIS
    try:
        service = get_push_analysis_service()
        if not service:
            logger.warning("Push analysis service not available")
            return
        result = asyncio.run(service.analyze_push(repo, before, after, commits))
        LAST_PUSH_ANALYSIS = result
    except Exception as e:
        logger.error(f"Push analysis error: {e}")


# ============ Routes ============

@app.route("/webhook", methods=["POST"])
def webhook():
    """GitHub webhook endpoint"""
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    payload = request.data
    signature = request.headers.get("x-hub-signature-256", "")
    
    # Verify signature if secret is set
    if secret and not verify_signature(secret, payload, signature):
        logger.warning("Invalid webhook signature")
        return jsonify({"error": "Invalid signature"}), 401
    
    try:
        event = request.get_json(force=True)
        event_name = request.headers.get("x-github-event", "unknown")
        
        # Extract PR info if available
        if event_name == "pull_request":
            pr = event.get("pull_request", {})
            ev = {
                "event_name": "pull_request",
                "action": event.get("action"),
                "summary": {
                    "pr_number": pr.get("number"),
                    "title": pr.get("title"),
                    "author": pr.get("user", {}).get("login"),
                    "repo": event.get("repository", {}).get("full_name"),
                    "changed_files_count": pr.get("changed_files", 0),
                    "url": pr.get("html_url")
                }
            }
        elif event_name == "pull_request_review_comment":
            comment = event.get("comment", {})
            ev = {
                "event_name": "pull_request_review_comment",
                "action": event.get("action"),
                "summary": {
                    "pr_number": event.get("pull_request", {}).get("number"),
                    "repo": event.get("repository", {}).get("full_name"),
                    "comment_id": comment.get("id"),
                    "comment_body": comment.get("body"),
                    "path": comment.get("path"),
                }
            }
        elif event_name == "push":
            repo = event.get("repository", {}).get("full_name")
            before = event.get("before")
            after = event.get("after")
            commits = event.get("commits", []) or []
            ev = {
                "event_name": "push",
                "summary": {
                    "repo": repo,
                    "before": before,
                    "after": after,
                    "commit_count": len(commits),
                },
            }
        else:
            ev = {
                "event_name": event_name,
                "summary": event
            }
        
        push_event(ev)
        logger.info(f"Received {event_name} event")
        
        # Analyze in background if it's a PR event
        if event_name == "pull_request":
            thread = threading.Thread(
                target=analyze_event_background,
                args=(ev,),
                daemon=True
            )
            thread.start()

            if os.getenv("REVIEW_AUTO", "1") == "1":
                repo = ev.get("summary", {}).get("repo")
                pr_number = ev.get("summary", {}).get("pr_number")
                if repo and pr_number:
                    review_thread = threading.Thread(
                        target=review_pr_background,
                        args=(repo, pr_number),
                        daemon=True
                    )
                    review_thread.start()

        if event_name == "pull_request_review_comment":
            if os.getenv("REVIEW_REPLY_ENABLED", "1") == "1":
                reply_thread = threading.Thread(
                    target=reply_review_comment_background,
                    args=(event,),
                    daemon=True
                )
                reply_thread.start()
        
        if event_name == "push":
            repo = event.get("repository", {}).get("full_name")
            before = event.get("before")
            after = event.get("after")
            commits = event.get("commits", []) or []
            if not repo or not before or not after:
                return jsonify({"status": "error", "message": "missing push metadata"}), 400

            sync = os.getenv("PUSH_ANALYSIS_SYNC", "1") == "1"
            if sync:
                service = get_push_analysis_service()
                if not service:
                    return jsonify({"status": "error", "message": "push analysis not available"}), 500
                result = asyncio.run(service.analyze_push(repo, before, after, commits))
                LAST_PUSH_ANALYSIS.clear()
                LAST_PUSH_ANALYSIS.update(result)
                return jsonify({"status": "ok", "analysis": result}), 200

            thread = threading.Thread(
                target=analyze_push_background,
                args=(repo, before, after, commits),
                daemon=True,
            )
            thread.start()
            return jsonify({"status": "ok", "message": "push analysis started"}), 200

        return jsonify({"status": "ok"}), 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"error": "webhook error"}), 400


@app.route("/", methods=["GET"])
def ui_summary():
    """Show latest push analysis summary"""
    summary = LAST_PUSH_ANALYSIS.get("summary", "")
    key_changes = LAST_PUSH_ANALYSIS.get("key_changes", [])
    files_changed = LAST_PUSH_ANALYSIS.get("files_changed", [])
    impact = LAST_PUSH_ANALYSIS.get("impact_level", "")
    stats = LAST_PUSH_ANALYSIS.get("stats", {"files": 0, "additions": 0, "deletions": 0})

    file_summaries = []
    for idx, path in enumerate(files_changed):
        summary_text = key_changes[idx] if idx < len(key_changes) else ""
        file_summaries.append({"path": path, "summary": summary_text})

    return render_template_string(
        UI_TEMPLATE,
        summary=summary,
        impact=impact or "Medium",
        stats=stats,
        files=file_summaries,
    )


@app.route("/api/push-analysis", methods=["GET"])
def get_push_analysis():
    """Return latest push analysis"""
    return jsonify(LAST_PUSH_ANALYSIS or {}), 200


@app.route("/api/events", methods=["GET"])
def get_recent_events():
    """Return recent webhook events (debug)"""
    with EVENTS_LOCK:
        events = list(RECENT_EVENTS)[-50:]
    return jsonify({"count": len(events), "events": events}), 200


@app.route("/api/events/last", methods=["GET"])
def get_last_event():
    """Return the last webhook event (debug)"""
    with EVENTS_LOCK:
        last = RECENT_EVENTS[-1] if RECENT_EVENTS else None
    return jsonify({"event": last}), 200


@app.route("/api/health", methods=["GET"])
def health():
    """Health check"""
    return jsonify({
        "status": "ok",
        "version": "2.0.0",
        "integration_available": IntegrationLayer is not None,
        "timestamp": datetime.utcnow().isoformat()
    })


# ============ Error Handlers ============

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Server error: {error}")
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    # Initialize integration layer
    get_integration_layer()
    
    # Run server
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        debug=os.getenv("DEBUG", "false").lower() == "true"
    )
