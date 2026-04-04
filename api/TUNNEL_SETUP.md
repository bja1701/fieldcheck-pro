# Cloudflare Named Tunnel Setup

A named tunnel gives you a **stable URL** (`https://<uuid>.cfargotunnel.com`) that never changes between restarts. Do this once.

## Prerequisites

- `cloudflared` installed (already present on this machine)
- A free Cloudflare account at cloudflare.com

---

## Step 1 — Log in to Cloudflare (one time)

```bash
cloudflared tunnel login
```

A browser window opens. Log in and authorize the certificate. This saves `~/.cloudflared/cert.pem`.

---

## Step 2 — Create the named tunnel (one time)

```bash
cloudflared tunnel create fieldcheck-api
```

Output will show a **tunnel UUID** like `abc12345-...`. Note it — this is your permanent tunnel ID.

Your stable URL is:
```
https://<tunnel-uuid>.cfargotunnel.com
```

`cloudflared` also writes **`~/.cloudflared/<tunnel-uuid>.json`** (credentials). You need this path in the next step.

---

## Step 3 — Create `~/.cloudflared/config.yml` (required)

Without this file, `cloudflared tunnel run` connects to Cloudflare but **has no ingress rules**, so every request fails (browser: “Failed to fetch”, `curl`: connection errors or 503). You will see a warning like *“No ingress rules were defined”*.

1. Copy the example and edit it (use your **real** tunnel UUID and **absolute** paths):

   ```bash
   cp projects/hobble-creek-plumbing/api/cloudflared-config.example.yml ~/.cloudflared/config.yml
   ```

2. Edit `~/.cloudflared/config.yml`:
   - `tunnel:` must equal your tunnel UUID (same as in the URL).
   - `credentials-file:` must be the absolute path to `~/.cloudflared/<tunnel-uuid>.json` from Step 2 (e.g. `/home/you/.cloudflared/1aadb92a-....json`).
   - `service:` must be `http://127.0.0.1:8000` (same port as `start.sh`; use `127.0.0.1` so `cloudflared` does not depend on IPv6 `localhost` quirks).

3. Test:

   ```bash
   curl -sS "https://<tunnel-uuid>.cfargotunnel.com/api/health"
   ```

   With `start.sh` running, you should see `{"status":"ok"}`.

**WSL:** Run `start.sh` and `curl` from the same Linux environment. Paths in `config.yml` are Linux paths under `/home/...`, not `C:\`.

---

## Step 4 — Update supabase-config.js

Open `frontend/supabase-config.js` and replace `REPLACE_WITH_TUNNEL_URL` with your stable URL:

```js
window.API_SERVER_URL = 'https://<tunnel-uuid>.cfargotunnel.com';
```

Then redeploy to Vercel (`vercel --prod` from `frontend/`).

---

## Step 5 — Start the server + tunnel

From the `nexusflow_builds/` root:

```bash
./projects/hobble-creek-plumbing/api/start.sh
```

That's it. Every time you run this, the tunnel comes up at the same URL.

---

## Quick Tunnel (no setup, random URL)

If you just want to test without the named tunnel:

```bash
TUNNEL_MODE=quick ./projects/hobble-creek-plumbing/api/start.sh
```

The URL printed in the console changes every restart, so you'd need to update `supabase-config.js` each time.

---

## Environment Variables

The server reads these from `nexusflow_builds/.env`:

| Variable | Required | Description |
|---|---|---|
| `SUPABASE_SERVICE_ROLE` | Yes | Service role key — allows pipeline to publish results to Supabase |
| `GOOGLE_API_KEY` | Yes | Gemini API key for the matching LLM |

Make sure `.env` is populated before starting.
