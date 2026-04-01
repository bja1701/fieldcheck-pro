# FieldCheck Pro — Hobble Creek Plumbing

Bid-vs-spec verification tool for Hobble Creek Plumbing (client: Chad Baker / Scott).
A foreman uploads four documents; the system checks whether what was bid matches what the homeowner actually specified, then flags discrepancies for the office.

---

## What It Does

1. **Foreman opens** `https://fieldcheck-pro.vercel.app` on their phone or laptop
2. **Uploads** four job documents — bid sheet, spec book URL, house plans PDF, cabinet drawings PDF
3. **Pipeline runs** on Brighton's local machine (triggered via API) and processes everything with AI
4. **Results appear** in the web UI: green = match, yellow = extra in bid, red = missing from bid

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Vercel (fieldcheck-pro.vercel.app)                             │
│  Static HTML/JS — login, projects list, job view               │
│  Reads job data from Supabase                                   │
└──────────────────────┬──────────────────────────────────────────┘
                       │ POST /api/run-pipeline
                       │ GET  /api/project-status
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Cloudflare Named Tunnel (fieldcheck-api)                       │
│  Stable URL: https://1aadb92a-fd85-4c76-bac3-368528954a0d      │
│                       .cfargotunnel.com                         │
│  Routes HTTPS → localhost:8000                                  │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI Server (api/server.py) — port 8000                     │
│  Downloads files, runs pipeline in background thread            │
│  Tracks job status in memory                                    │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  LangGraph Pipeline (graph.py)                                  │
│  8 nodes: parse_bid → scrape_spec → extract_plans →             │
│           extract_cabinets → map_rooms → match_items →          │
│           generate_output → publish_to_supabase                 │
└──────────────────────┬──────────────────────────────────────────┘
                       │ PATCH projects.generated_data
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Supabase (ftidlgjmtiyuxycaacob.supabase.co)                    │
│  Tables: projects, project_documents, project_images            │
│  Storage: project-files (uploads), project-images (outputs)     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Repo Structure

```
nexusflow_builds/                  ← git root (github.com/bja1701/fieldcheck-pro)
├── pyproject.toml                 ← Python deps (uv)
├── projects/
│   └── hobble-creek-plumbing/
│       ├── README.md              ← this file
│       ├── blueprint.md           ← detailed pipeline spec (what each step does)
│       ├── graph.py               ← LangGraph entry point + CLI
│       ├── state.py               ← FieldCheckState TypedDict (shared by all nodes)
│       ├── nodes/                 ← one file per pipeline node
│       │   ├── parse_bid.py
│       │   ├── scrape_spec.py
│       │   ├── extract_plans.py
│       │   ├── extract_cabinets.py
│       │   ├── map_rooms.py
│       │   ├── match_items.py
│       │   ├── generate_output.py
│       │   └── publish_to_supabase.py
│       ├── tests/                 ← pytest — one test file per node (181 tests)
│       ├── fixtures/              ← sample input files for tests
│       ├── cache/                 ← cached specbooks API responses (saves API calls)
│       ├── frontend/              ← Vercel static site (HTML + JS)
│       │   ├── login.html
│       │   ├── projects.html
│       │   ├── job.html
│       │   ├── bid-check.html
│       │   ├── js/                ← Alpine.js modules (app-state, billable, etc.)
│       │   ├── supabase-config.js ← Supabase URL/key + API server URL
│       │   ├── vercel.json        ← Vercel routing config
│       │   └── .gitignore
│       └── api/
│           ├── server.py          ← FastAPI server (wraps the pipeline)
│           ├── start.sh           ← ONE COMMAND to start everything
│           └── TUNNEL_SETUP.md    ← How the Cloudflare tunnel was set up
```

---

## Day-to-Day: Starting the System

Run this one command from `nexusflow_builds/` whenever you want the pipeline to be available:

```bash
cd ~/nexusflow_builds
./projects/hobble-creek-plumbing/api/start.sh
```

This starts:
- FastAPI server on `localhost:8000`
- Named Cloudflare tunnel (`fieldcheck-api`) → exposes the server at the stable public URL

The Vercel frontend is always live at `https://fieldcheck-pro.vercel.app`. The tunnel only needs to be running when processing a job.

**To stop:** `Ctrl+C` in the terminal running `start.sh`.

---

## Environment Variables

These live in `nexusflow_builds/.env`. Create this file if it doesn't exist:

```bash
# Required for pipeline to work
SUPABASE_SERVICE_ROLE=eyJ...    # Service role key (bypasses RLS — never commit)
GOOGLE_API_KEY=AIza...          # Gemini API key (free tier works)

# Optional
TUNNEL_NAME=fieldcheck-api      # Default tunnel name (matches what was created)
```

Get these from:
- `SUPABASE_SERVICE_ROLE` → Supabase Dashboard → Project Settings → API → service_role key
- `GOOGLE_API_KEY` → https://aistudio.google.com/apikey

---

## First-Time Setup (New Machine)

If you need to set this up on a new machine from scratch:

### 1. Clone and install deps

```bash
git clone git@github.com:bja1701/fieldcheck-pro.git nexusflow_builds
cd nexusflow_builds
curl -LsSf https://astral.sh/uv/install.sh | sh   # install uv if needed
uv sync
```

### 2. Install system dependencies

```bash
# Ubuntu/Debian
sudo apt install poppler-utils    # pdftotext + pdftoppm (PDF processing)
```

### 3. Set up .env

```bash
cp .env.example .env   # if it exists, otherwise create manually
# Fill in SUPABASE_SERVICE_ROLE and GOOGLE_API_KEY
```

### 4. Install Cloudflare tunnel

```bash
# Download from https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
# Or on Ubuntu:
wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb
```

### 5. Set up the named tunnel (one time)

See `api/TUNNEL_SETUP.md` for the full walkthrough. Short version:

```bash
cloudflared tunnel login              # opens browser — authorize once
cloudflared tunnel create fieldcheck-api
# → prints tunnel UUID — copy it

# Required: add ~/.cloudflared/config.yml with ingress → http://127.0.0.1:8000
# (see api/cloudflared-config.example.yml and api/TUNNEL_SETUP.md Step 3)

# Update frontend/supabase-config.js line:
# window.API_SERVER_URL = 'https://<your-uuid>.cfargotunnel.com';

# Then redeploy frontend (see below)
```

**Current tunnel UUID:** `1aadb92a-fd85-4c76-bac3-368528954a0d`
**Current stable URL:** `https://1aadb92a-fd85-4c76-bac3-368528954a0d.cfargotunnel.com`

### 6. Install Vercel CLI and log in

```bash
npm install -g vercel
vercel login   # opens browser
```

### 7. Start the system

```bash
./projects/hobble-creek-plumbing/api/start.sh
```

---

## Deploying Frontend Changes

When you edit any file in `frontend/`:

```bash
cd ~/nexusflow_builds/projects/hobble-creek-plumbing/frontend
vercel --prod
```

Vercel will prompt to link to existing project — say yes, pick `fieldcheck-pro`.

---

## Running the Pipeline Manually (No UI)

You can run the pipeline directly from CLI without the web UI:

```bash
cd ~/nexusflow_builds
uv run python projects/hobble-creek-plumbing/graph.py \
  --spec-url "https://specbooks.com/v4/especbook/3408205?token=YOUR_TOKEN" \
  --bid "path/to/bid.xlsx" \
  --plans "path/to/plans.pdf" \
  --cabinets "path/to/cabinets.pdf" \
  --job-name "Baker Residence" \
  --output-dir "/tmp/job-output" \
  --project-id "supabase-project-uuid"    # optional — skips Supabase publish if omitted
```

Output goes to `--output-dir`. If `--project-id` is set, results are also uploaded to Supabase and appear in the web UI.

---

## Running Tests

```bash
cd ~/nexusflow_builds
uv run pytest projects/hobble-creek-plumbing/tests/ -v
# 181 tests, all should pass
```

---

## How the Pipeline Works (Summary)

See `blueprint.md` for full detail. Quick version:

| Step | Node | What it does |
|------|------|-------------|
| 1 | `parse_bid` | Read XLSX/CSV bid sheet → extract room/item/qty/price |
| 2 | `scrape_spec` | Hit specbooks.com API with token → download all items + images |
| 3 | `extract_plans` | Convert plans PDF → JPGs, detect which floor each page belongs to |
| 4 | `extract_cabinets` | Convert cabinets PDF → PNGs, detect which room each page belongs to |
| 5 | `map_rooms` | Gemini AI: match spec room names to bid room names |
| 6 | `match_items` | Gemini AI: for each bid item, find matching spec item(s) with billing rules |
| 7 | `generate_output` | Build `JOB_DATA` structure → write `data.js` |
| 8 | `publish_to_supabase` | Upload images + push `generated_data` → Supabase projects table |

Any node that sets `state["error"]` short-circuits the rest of the pipeline.

---

## Key Business Rules

- **Spec book is the source of truth** — room names in the output follow the spec, not the bid
- **Plan-sourced items** (Hose Bib, Washer Box, Ice bin hook-up, Refrigerator Water-Line, Dog Wash) skip AI matching — they come from plans, not the spec book
- **Billing rules** — "Lav" = faucet (not the sink bowl), "Shower" = showerhead (not trim/valve), etc. — see `match_items.py` `BILLING_RULES`
- **Confidence threshold** — matches below 0.85 go to the review queue but still appear in the output
- **Urinal fallback** — if a urinal isn't found in the room's spec items, search all rooms cross-room

---

## Known Limitations

- **Local-only pipeline** — the server must be running on Brighton's machine. If the machine is off or the tunnel is down, uploads will hang. A future paid plan could move this to Railway or Fly.io.
- **In-memory job state** — if the server restarts mid-job, that job's status is lost (the pipeline result still publishes to Supabase, but the polling UI will show "pending" forever). Retry from the job page.
- **Specbooks token expiry** — the token in the spec URL expires. If scraping returns 0 items, the token has expired — ask Chad to re-share the URL.

---

## Supabase Schema (Quick Reference)

| Table | Key columns |
|-------|-------------|
| `projects` | `id`, `name`, `status` (pending/processing/review/complete/error), `generated_data` (JSONB — the full JOB_DATA) |
| `project_documents` | `project_id`, `doc_type` (spec_url/bid_spreadsheet/plans_pdf/cabinets_pdf), `file_path`, `spec_url` |

Storage buckets:
- `project-files` — raw uploaded documents (bid, plans, cabinets)
- `project-images` — pipeline output images (spec images, plan pages, cabinet pages)

---

## Contacts / Context

- **Client:** Chad Baker + Scott (field user) — Hobble Creek Plumbing
- **Problem solved:** Chad's office bids jobs using a spec book; field techs need to know what was actually bid so they can flag change orders
- **Demo history:** Failed demo 3/26 (specbooks token expired). Scott meeting 3/26 identified additional matching rules (urinals, shower sub-items, plan-sourced items)
- **GitHub:** `github.com/bja1701/fieldcheck-pro`
- **Vercel project:** `fieldcheck-pro` under Brighton's scope
