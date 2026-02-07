# Repo Monitor Agent

Minimal setup for webhook PR review + GitHub Actions flow.

## What’s included
- Webhook server: [server/app_enhanced.py](server/app_enhanced.py)
- PR review runner for Actions: [scripts/run_pr_review.py](scripts/run_pr_review.py)
- Workflow: [.github/workflows/pr-review.yml](.github/workflows/pr-review.yml)

## Webhook server
Start the server (Foundry Local example):

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
