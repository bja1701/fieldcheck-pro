#!/usr/bin/env bash
# FieldCheck Pro — Start quick Cloudflare tunnel and auto-update supabase-config.js
#
# Each run gets a new trycloudflare.com URL. This script:
#   1. Starts the quick tunnel
#   2. Parses the public URL from cloudflared output
#   3. Updates frontend/supabase-config.js with the new URL
#   4. Commits + pushes so Vercel auto-redeploys the frontend
#
# Run as: systemd service (fieldcheck-tunnel) from the repo root.

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_JS="$REPO_DIR/frontend/supabase-config.js"
LOG="/tmp/fieldcheck-tunnel-raw.log"

cd "$REPO_DIR"

echo "[tunnel-start] Starting quick Cloudflare tunnel…"

# Start cloudflared quick tunnel, pipe output to log and stdout
cloudflared tunnel --url http://127.0.0.1:8000 2>&1 | tee "$LOG" &
CF_PID=$!

# Wait for cloudflared to print the public URL (up to 30s)
TUNNEL_URL=""
for i in $(seq 1 30); do
    sleep 1
    TUNNEL_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" 2>/dev/null | head -1)
    if [ -n "$TUNNEL_URL" ]; then
        break
    fi
done

if [ -z "$TUNNEL_URL" ]; then
    echo "[tunnel-start] ERROR: Could not detect tunnel URL after 30s"
    kill "$CF_PID" 2>/dev/null || true
    exit 1
fi

echo "[tunnel-start] Tunnel URL: $TUNNEL_URL"

# Update supabase-config.js — replace the API_SERVER_URL assignment line (handles any suffix)
sed -i "s|window\.API_SERVER_URL = '.*|window.API_SERVER_URL = '$TUNNEL_URL';|" "$CONFIG_JS"

echo "[tunnel-start] Updated supabase-config.js with $TUNNEL_URL"

# Commit and push so Vercel redeploys
git -C "$REPO_DIR" add frontend/supabase-config.js
if git -C "$REPO_DIR" diff --cached --quiet; then
    echo "[tunnel-start] supabase-config.js unchanged — URL same as last run"
else
    git -C "$REPO_DIR" commit -m "chore: update tunnel URL to $TUNNEL_URL [skip ci]"
    git -C "$REPO_DIR" push origin master
    echo "[tunnel-start] Pushed new tunnel URL — Vercel will redeploy"
fi

# Wait for cloudflared to exit (keeps the service alive)
wait "$CF_PID"
