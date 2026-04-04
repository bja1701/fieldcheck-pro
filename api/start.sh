#!/usr/bin/env bash
# FieldCheck Pro — Start API server + Cloudflare tunnel
#
# Usage:
#   ./api/start.sh                        # named tunnel (stable URL, requires setup)
#   TUNNEL_MODE=quick ./api/start.sh      # quick tunnel (random URL, no setup needed)
#
# Run from the fieldcheck-pro repo root directory.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load .env if present (SUPABASE_SERVICE_ROLE, GOOGLE_API_KEY)
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

PORT=8000

echo "Starting FieldCheck Pro API server on port $PORT…"

# Start uvicorn in background
uv run uvicorn api.server:app \
    --host 0.0.0.0 \
    --port "$PORT" &
SERVER_PID=$!

sleep 2  # give server a moment to bind

CLOUDFLARED_HOME="${HOME}/.cloudflared"
CF_CONFIG="${CLOUDFLARED_CONFIG:-}"
if [ -z "$CF_CONFIG" ]; then
  if [ -f "${CLOUDFLARED_HOME}/config.yml" ]; then
    CF_CONFIG="${CLOUDFLARED_HOME}/config.yml"
  elif [ -f "${CLOUDFLARED_HOME}/config.yaml" ]; then
    CF_CONFIG="${CLOUDFLARED_HOME}/config.yaml"
  fi
fi

# Start Cloudflare tunnel
if [ "${TUNNEL_MODE:-named}" = "quick" ]; then
    echo "Starting quick tunnel (random URL — not stable)…"
    cloudflared tunnel --url "http://localhost:$PORT"
else
    if [ -z "$CF_CONFIG" ] || [ ! -f "$CF_CONFIG" ]; then
        echo ""
        echo "ERROR: Named tunnel needs a Cloudflare config with ingress rules."
        echo "  Expected: ~/.cloudflared/config.yml (or set CLOUDFLARED_CONFIG)"
        echo "  Without it, cloudflared logs: 'No ingress rules' and the public URL will not reach this API."
        echo "  Fix: copy api/cloudflared-config.example.yml to ~/.cloudflared/config.yml"
        echo "  and set tunnel + credentials-file. See api/TUNNEL_SETUP.md Step 3."
        echo ""
        echo "Or use a one-off tunnel (new URL each run):"
        echo "  TUNNEL_MODE=quick $0"
        echo ""
        kill "$SERVER_PID" 2>/dev/null || true
        exit 1
    fi
    TUNNEL_NAME="${TUNNEL_NAME:-fieldcheck-api}"
    echo "Starting named tunnel '$TUNNEL_NAME' with config: $CF_CONFIG"
    cloudflared tunnel --config "$CF_CONFIG" run "$TUNNEL_NAME"
fi

# Cleanup server when tunnel exits
kill "$SERVER_PID" 2>/dev/null || true
