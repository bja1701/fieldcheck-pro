#!/usr/bin/env bash
# FieldCheck Pro — Start API server + Cloudflare tunnel
#
# Usage:
#   ./api/start.sh                        # named tunnel (stable URL, requires setup)
#   TUNNEL_MODE=quick ./api/start.sh      # quick tunnel (random URL, no setup needed)
#
# Run from the nexusflow_builds/ root directory.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILDS_DIR="$(dirname "$(dirname "$PROJECT_DIR")")"

# Load .env if present (SUPABASE_SERVICE_ROLE, GOOGLE_API_KEY)
if [ -f "$BUILDS_DIR/.env" ]; then
    set -a
    source "$BUILDS_DIR/.env"
    set +a
fi

PORT=8000

echo "Starting FieldCheck Pro API server on port $PORT…"

# Start uvicorn in background
uv run uvicorn projects.hobble-creek-plumbing.api.server:app \
    --host 0.0.0.0 \
    --port "$PORT" &
SERVER_PID=$!

sleep 2  # give server a moment to bind

# Start Cloudflare tunnel
if [ "${TUNNEL_MODE:-named}" = "quick" ]; then
    echo "Starting quick tunnel (random URL — not stable)…"
    cloudflared tunnel --url "http://localhost:$PORT"
else
    TUNNEL_NAME="${TUNNEL_NAME:-fieldcheck-api}"
    echo "Starting named tunnel '$TUNNEL_NAME' (stable URL)…"
    echo "Your tunnel URL: check ~/.cloudflared/ for the tunnel UUID after first run."
    cloudflared tunnel run "$TUNNEL_NAME"
fi

# Cleanup server when tunnel exits
kill "$SERVER_PID" 2>/dev/null || true
