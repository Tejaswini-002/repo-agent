# Repo Monitor Agent (Step 1 — No LLM)

This repo provides a **sure working** "Step 1" monitoring agent for GitHub repositories.

✅ Monitors **every push/commit** on **all branches**  
✅ Monitors PR updates (opened / reopened / synchronize)  
✅ Prints commit + changed files in **GitHub Actions logs**  
✅ (Optional) Leaves a simple confirmation comment on PR

---

## 1) What you get

- `.github/workflows/repo-monitor.yml`  
  Runs on every push and PR update.
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
python3 scripts/monitor.py
```

### Windows (PowerShell)
```powershell
python scripts/monitor.py
```

You should see:
- latest commit details
- changed file list
- diff summary

---

## 4) How to verify the agent is working on GitHub

### A) Verify push/commit monitoring
1. Make any change in your repo
2. Commit + push
3. Go to your repo → **Actions** tab → **Repo Monitor Agent**
4. Open the latest run
5. In logs, you should see:
   - Event: push
   - SHA
   - Latest commit
   - Changed files

### B) Verify PR monitoring
1. Create a PR (or push new commits to an existing PR branch)
2. Go to **Actions** tab and open the run
3. (Optional) Check PR timeline — you should see a comment:
   **✅ Repo Monitor Agent**

---

## 5) Troubleshooting

### PR comment not showing up?
Repo → **Settings → Actions → General** → **Workflow permissions**  
Set to:
- ✅ **Read and write permissions**

Then rerun workflow or push again.

### Workflow not running at all?
- Ensure the workflow file path is exactly:
  `.github/workflows/repo-monitor.yml`
- Ensure GitHub Actions are enabled in the repo settings.

---

## Notes
- No ngrok, no webhooks, no server required for Step 1.
- This is the best starting point for “monitor my repo and commits”.

---

## Real-time Webhook UI (optional)

This repository includes an optional Flask-based webhook server and a tiny UI that streams PR events in real time.

Files added:
- `server/app.py` — Flask server handling `/webhook` and Server-Sent Events `/events`.
- `server/templates/index.html` — live UI that connects to `/events`.
- `server/pdf_logger.py` — PDF export for PR event summaries.

### Quick start with ngrok (helper script)

If you have ngrok installed, the repository includes a convenience script to start the Flask server + ngrok and print the public webhook URL.

1. Make the helper executable:

```bash
chmod +x scripts/start_with_ngrok.sh
```

2. Run it (optional: pass `PORT` and `SECRET`):

```bash
./scripts/start_with_ngrok.sh 5002 your-webhook-secret
```

The script starts the server and ngrok, then prints the public `https://.../webhook` URL you should enter into your GitHub App webhook settings (Content type: `application/json`).

3. (Optional) Use the `.env.example` as a starting point for environment variables.

Note: This helper assumes you have the `ngrok` binary installed and available on your PATH. It uses ngrok's local API at `http://127.0.0.1:4040` to discover the public tunnel URL.

### Manual setup (recommended)

1. Install dependencies:

```bash
pip3 install -r requirements.txt
```

2. Create a `.env` file (copy from `.env.example` and fill in your secrets):

```bash
cp .env.example .env
# Edit .env with your webhook secret and GitHub token
```

3. Start the server:

```bash
export $(grep -v '^#' .env | xargs)
python3 server/app.py
```

   Server runs at `http://localhost:5002` (or your chosen `PORT`).

4. Open the UI in a browser at `http://localhost:5002/`.

5. Configure your GitHub App webhook to post to your server (via ngrok or direct URL):
   - Webhook URL: `https://<your-public-url>/webhook/github` (supports both `/webhook` and `/webhook/github`)
   - Content type: `application/json`
   - Secret: set to the same value as `GITHUB_WEBHOOK_SECRET` in your `.env`
   - Events: subscribe to "Pull request"

### Available endpoints

- `GET /` — Live UI showing PR events in real-time
- `POST /webhook` or `POST /webhook/github` — Receives GitHub webhook payloads
- `GET /events` — Server-Sent Events stream of all events (consumed by UI)
- `GET /health` — Health check
- `GET /stats` — Statistics (event count, PDF support status)
- `GET /pdf` — Export recent PR events as a PDF report

### Environment variables

- `PORT` — port the server listens on (default: 5000)
- `GITHUB_WEBHOOK_SECRET` — HMAC secret to validate incoming webhooks (optional but recommended)
- `GITHUB_TOKEN` — GitHub API token to fetch PR file lists (optional; if set, enables detailed file change reporting)
- `MONITOR_EVENTS_PATH` — path to append JSONL events (default: `repo-monitor-events.jsonl`)

### PDF export

The server can export PR event summaries as a formatted PDF:

```bash
# Export and download
curl http://localhost:5002/pdf -o pr_report.pdf

# Or via the UI
```

The PDF includes:
- Event timestamp, PR number, action (opened/synchronize/etc)
- Repository, title, author
- Changed files count and detailed file list (if fetched via GITHUB_TOKEN)
