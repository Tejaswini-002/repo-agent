#!/usr/bin/env python3
"""Webhook server + live UI for Repo Monitor Agent

Features:
- Receives GitHub webhooks at /webhook (validates signature if GITHUB_WEBHOOK_SECRET set)
- Streams real-time events to connected browsers via Server-Sent Events at /events
- Simple single-page UI at /
- Optionally fetches changed file list for PRs when GITHUB_TOKEN is provided
- Exports PR summaries to PDF
"""
from flask import Flask, request, Response, render_template, jsonify, send_file
import hmac
import hashlib
import os
import json
import threading
import time
from datetime import datetime
from typing import List
from pdf_logger import generate_pdf_report, HAS_REPORTLAB

app = Flask(__name__, template_folder="templates")

# In-memory store of recent events (capped)
EVENTS_LOCK = threading.Lock()
RECENT_EVENTS: List[dict] = []
MAX_EVENTS = 200


def verify_signature(secret: str, payload: bytes, signature_header: str) -> bool:
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
    ev["timestamp"] = datetime.utcnow().isoformat() + "Z"
    with EVENTS_LOCK:
        RECENT_EVENTS.append(ev)
        if len(RECENT_EVENTS) > MAX_EVENTS:
            RECENT_EVENTS.pop(0)
    # also append to disk so Actions can upload it (same file as monitor.py)
    try:
        path = os.getenv("MONITOR_EVENTS_PATH", "repo-monitor-events.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except Exception:
        pass


def fetch_pr_files(repo: str, pr_number: int, token: str):
    try:
        import requests
    except Exception:
        requests = None

    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/files"
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    files = []
    page = 1
    per_page = 100
    while True:
        paged = f"{url}?page={page}&per_page={per_page}"
        try:
            if requests:
                r = requests.get(paged, headers=headers, timeout=10)
                r.raise_for_status()
                batch = r.json()
            else:
                import urllib.request
                req = urllib.request.Request(paged)
                for k, v in headers.items():
                    req.add_header(k, v)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    batch = json.load(resp)
        except Exception:
            break
        if not batch:
            break
        for f in batch:
            files.append({"filename": f.get("filename"), "status": f.get("status")})
        if len(batch) < per_page:
            break
        page += 1
        if len(files) >= 500:
            break
    return files


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/pdf", methods=["GET"])
def export_pdf():
    """Export recent PR events as a PDF report"""
    if not HAS_REPORTLAB:
        return jsonify({"error": "reportlab not installed. Install via: pip install reportlab"}), 400
    
    try:
        with EVENTS_LOCK:
            pr_events = [ev for ev in RECENT_EVENTS if ev.get("event_name") == "pull_request"]
        
        if not pr_events:
            return jsonify({"error": "No PR events to export"}), 404
        
        pdf_path = f"/tmp/pr_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
        if generate_pdf_report(pr_events, pdf_path):
            return send_file(pdf_path, mimetype="application/pdf", as_attachment=True, download_name="pr_events_report.pdf")
        else:
            return jsonify({"error": "Failed to generate PDF"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/stats", methods=["GET"])
def stats():
    """Return event statistics"""
    with EVENTS_LOCK:
        total = len(RECENT_EVENTS)
        pr_count = len([ev for ev in RECENT_EVENTS if ev.get("event_name") == "pull_request"])
    
    return jsonify({
        "total_events": total,
        "pr_events": pr_count,
        "max_events_cached": MAX_EVENTS,
        "reportlab_available": HAS_REPORTLAB,
    })


@app.route("/webhook", methods=["POST"])
@app.route("/webhook/github", methods=["POST"])  # alias for GitHub App webhook URL
def webhook():
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    signature = request.headers.get("X-Hub-Signature-256", "")
    payload = request.get_data()

    if secret:
        if not verify_signature(secret, payload, signature):
            return "Invalid signature", 403

    event = request.headers.get("X-GitHub-Event", "")
    try:
        payload_obj = request.get_json(force=True)
    except Exception:
        payload_obj = {}

    if event == "pull_request":
        pr = payload_obj.get("pull_request", {})
        action = payload_obj.get("action")
        repo = payload_obj.get("repository", {}).get("full_name")
        pr_number = pr.get("number")
        title = pr.get("title")
        user = pr.get("user", {}).get("login")
        changed_files_count = pr.get("changed_files")

        summary = {
            "type": "pull_request",
            "repo": repo,
            "action": action,
            "pr_number": pr_number,
            "title": title,
            "user": user,
            "changed_files_count": changed_files_count,
            "url": pr.get("html_url"),
        }

        token = os.getenv("GITHUB_TOKEN")
        files = []
        if token and repo and pr_number:
            try:
                files = fetch_pr_files(repo, int(pr_number), token)
            except Exception:
                files = []

        if files:
            summary["files"] = files[:200]
        push_event({"event_name": "pull_request", "summary": summary})
        return "OK", 200

    push_event({"event_name": event, "payload": payload_obj})
    return "OK", 200


@app.route("/events")
def sse_events():
    def gen():
        with EVENTS_LOCK:
            for ev in RECENT_EVENTS:
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

        last_index = len(RECENT_EVENTS)
        while True:
            time.sleep(0.5)
            with EVENTS_LOCK:
                if len(RECENT_EVENTS) > last_index:
                    for ev in RECENT_EVENTS[last_index:]:
                        yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                    last_index = len(RECENT_EVENTS)

    return Response(gen(), mimetype="text/event-stream")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
