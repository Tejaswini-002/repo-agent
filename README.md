# Repo Monitor Agent (Step 1)

This repo provides a **sure working** "Step 1" monitoring agent for GitHub repositories.

✅ Monitors **every push/commit** on **all branches**  
✅ Monitors PR updates (opened / reopened / synchronize)  
✅ Prints commit + changed files in **GitHub Actions logs**  
✅ (Optional) Leaves a simple confirmation comment on PRs (still no LLM)

---

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
