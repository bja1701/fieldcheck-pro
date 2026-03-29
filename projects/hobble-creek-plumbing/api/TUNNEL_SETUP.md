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

---

## Step 3 — Update supabase-config.js

Open `frontend/supabase-config.js` and replace `REPLACE_WITH_TUNNEL_URL` with your stable URL:

```js
window.API_SERVER_URL = 'https://<tunnel-uuid>.cfargotunnel.com';
```

Then redeploy to Vercel (`vercel --prod` from `frontend/`).

---

## Step 4 — Start the server + tunnel

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
