#!/usr/bin/env bash
set -euo pipefail
# Starts the Flask server and an ngrok tunnel, then prints the webhook URL to use in your GitHub App

PORT=${1:-5002}
SECRET=${2:-}

echo "Starting server on port $PORT..."
mkdir -p server
PORT=$PORT nohup python3 server/app.py > server/server-$PORT.log 2>&1 &
SERVER_PID=$!
echo "Server PID: $SERVER_PID (logs: server/server-$PORT.log)"

echo "Starting ngrok for port $PORT..."
ngrok http "$PORT" --log=stdout > /tmp/ngrok-$PORT.log 2>&1 &
NGROK_PID=$!
echo "ngrok PID: $NGROK_PID (logs: /tmp/ngrok-$PORT.log)"

echo "Waiting for ngrok to become available..."
for i in {1..20}; do
  sleep 0.5
  if curl -s http://127.0.0.1:4040/api/tunnels >/dev/null 2>&1; then
    break
  fi
done

TUNNELS_JSON=$(curl -s http://127.0.0.1:4040/api/tunnels || true)
PUBLIC_URL=$(echo "$TUNNELS_JSON" | python3 - <<PY
import sys, json
try:
    j = json.load(sys.stdin)
    t = j.get('tunnels') or []
    if t:
        print(t[0].get('public_url',''))
    else:
        print('')
except Exception:
    print('')
PY
)

if [ -z "$PUBLIC_URL" ]; then
  echo "Could not determine ngrok public URL. Check /tmp/ngrok-$PORT.log"
  exit 1
fi

echo
echo "ngrok public URL: $PUBLIC_URL"
echo "Use this webhook URL in your GitHub App settings (Content type: application/json):"
echo "  ${PUBLIC_URL}/webhook"
echo
if [ -n "$SECRET" ]; then
  echo "Secret provided. Run with:"
  echo "  GITHUB_WEBHOOK_SECRET=$SECRET PORT=$PORT python3 server/app.py"
fi

echo
echo "To stop: kill $SERVER_PID $NGROK_PID"
