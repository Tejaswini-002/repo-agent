# Repo Monitor Agent (Step 1)

Minimal setup for webhook PR review + GitHub Actions flow.

## What’s included
- Webhook server: [server/app_enhanced.py](server/app_enhanced.py)
- PR review runner for Actions: [scripts/run_pr_review.py](scripts/run_pr_review.py)
- Workflow: [.github/workflows/pr-review.yml](.github/workflows/pr-review.yml)

## Webhook server
Start the server (Foundry Local example):

## 1) What you get

- `.github/workflows/repo-monitor.yml`  
  Runs on every push and PR update
- `scripts/monitor.py`  
  Prints last commit info + changed files.
- `scripts/comment_pr.py`  
  Posts a simple PR comment on PR events (no LLM).

---

## 2) How to use in your repo

### A) Easiest: copy these files into your target repo
Copy into your repo:

- `.github/workflows/repo-monitor.yml`
- `scripts/monitor.py`
- `scripts/comment_pr.py`

Commit + push.

### B) Or: use this as a template repo
- Create a new repo on GitHub
- Upload these files (or push this repo)
- Enable Actions (default is enabled)

---

## 3) How to run locally (CMD)

> Local run is only for **testing**. Monitoring actually happens on GitHub via Actions.

### macOS / Linux
```bash
LLM_PROVIDER=foundry_local \
FOUNDRY_LOCAL_BASE_URL=http://localhost:8000 \
FOUNDRY_LOCAL_MODEL=qwen2.5-0.5b \
REVIEW_LIGHT_MODEL=qwen2.5-0.5b \
REVIEW_HEAVY_MODEL=qwen2.5-0.5b \
python3 -m server.app_enhanced
```

Webhook endpoint:
- `POST /webhook`

Health check:
- `GET /api/health`

## GitHub Actions
The workflow runs the PR review runner on `pull_request` and `pull_request_review_comment` events. Configure secrets as needed:
- `GITHUB_TOKEN`
- `FOUNDRY_LOCAL_BASE_URL`
- `FOUNDRY_LOCAL_MODEL`
- `FOUNDRY_LOCAL_API_KEY` (if required)
