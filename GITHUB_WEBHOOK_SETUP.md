# GitHub Webhook Setup for Tejaswini-002/repo-agent

This guide explains how to connect your GitHub repository to the Repo Monitor Agent.

## Prerequisites
- Access to https://github.com/Tejaswini-002/repo-agent repository settings
- Webhook receiver running (Flask app on port 5000)
- Public URL for webhook (use ngrok for local testing)

## Step 1: Get Public URL

If running locally, use ngrok to expose your webhook endpoint:

```bash
# Start ngrok (port 5000)
ngrok http 5000

# Copy the HTTPS URL, e.g., https://abc123.ngrok.io
```

## Step 2: Configure GitHub Webhook

1. Go to https://github.com/Tejaswini-002/repo-agent/settings/hooks
2. Click **Add webhook**
3. Configure:
   - **Payload URL**: `https://YOUR_NGROK_URL/webhook`
   - **Content type**: `application/json`
   - **Secret**: Generate a random string (save it!)
   - **Events**: Select:
     - [x] Pull requests
     - [x] Pull request reviews
     - [x] Pull request review comments
     - [x] Pushes (optional)
     - [x] Issues (optional)

4. Click **Add webhook**

## Step 3: Set Webhook Secret

Create a `.env` file in the project root:

```bash
# .env
GITHUB_WEBHOOK_SECRET=your_random_secret_here
```

Or export it:

```bash
export GITHUB_WEBHOOK_SECRET="your_random_secret_here"
```

## Step 4: Start Webhook Receiver

```bash
source .venv/bin/activate
python3 -m server.app_enhanced

# Or use the original app:
# python3 -m server.app
```

The webhook receiver will:
- Listen on http://localhost:5000/webhook
- Validate GitHub signatures
- Store events in `repo-monitor-events.jsonl`
- Trigger background PR analysis

## Step 5: Test the Webhook

1. Create a test PR in https://github.com/Tejaswini-002/repo-agent
2. Check the webhook delivery in GitHub settings
3. Verify events are logged:
   ```bash
   tail -f repo-monitor-events.jsonl
   ```
4. View analysis in dashboard at http://localhost:8501

## Webhook Event Flow

```
GitHub PR Event
    ↓
Webhook (validated)
    ↓
repo-monitor-events.jsonl
    ↓
PR Intelligence Engine (Foundry Local)
    ↓
Analysis Results
    ↓
Dashboard Display (Streamlit)
```

## Troubleshooting

**Webhook shows error in GitHub:**
- Check that ngrok is running
- Verify webhook secret matches `.env`
- Check the Flask server terminal output

**No analysis results:**
- Ensure Foundry Local is running and reachable
- Check dashboard logs
- Confirm `FOUNDRY_LOCAL_BASE_URL` and `FOUNDRY_LOCAL_MODEL` are set

**Signature validation fails:**
- Double-check `GITHUB_WEBHOOK_SECRET` matches GitHub settings
- Ensure secret is exported before starting server

## Advanced: Deploy to Production

For production deployment:

1. **Use a real domain** instead of ngrok
2. **Enable HTTPS** (required by GitHub)
3. **Set up systemd service** for webhook receiver
4. **Configure firewall** to allow port 5000 (or use reverse proxy)
5. **Enable logging** and monitoring

Example nginx config:

```nginx
server {
    listen 443 ssl;
    server_name webhooks.example.com;

    location /webhook {
        proxy_pass http://localhost:5000;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $host;
    }
}
```

---

**Repository**: https://github.com/Tejaswini-002/repo-agent  
**Dashboard**: http://localhost:8501  
**Webhook Endpoint**: http://localhost:5000/webhook
