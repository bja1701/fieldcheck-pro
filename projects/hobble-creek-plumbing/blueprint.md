# Automation Blueprint — FieldCheck Pro Pipeline
## Hobble Creek Plumbing / Chad Baker

---

## 1. Trigger
**What starts this automation?**
- [x] Manual — Brighton runs it from CLI for each new job

Command:
```bash
uv run python projects/hobble-creek-plumbing/graph.py \
  --spec-url "https://specbooks.com/v4/especbook/3408205?token=abc123" \
  --bid "Baker_Bid.xlsx" \
  --plans "plans.pdf" \
  --cabinets "cabinets.pdf" \
  --job-name "Baker Residence" \
  --output-dir "/home/frank/PAI/fieldcheck-pro"
```

Later (Phase 2): triggered via web UI when Chad uploads documents and clicks "Run Pipeline."

---

## 2. Input Data

| Input | Format | Notes |
|-------|--------|-------|
| Spec book URL | specbooks.com URL with `?token=` | Always specbooks.com |
| Bid sheet | CSV or XLSX/XLSM | Columns: ROOM, ITEM, QTY, PRICE |
| House plans | PDF | Multi-page; each page = one or more rooms on a floor |
| Cabinet drawings | PDF | Multi-page; each page = cabinets for one room |

---

## 3. What It Does (Step by Step)

### Step 1 — Parse Bid Sheet
- Read CSV or XLSX/XLSM bid sheet
- Extract all line items: room name, item name, quantity, unit price
- Skip summary/total rows
- Items with no spec equivalent (Water Heater, Sump Pump, Floor Drain, etc.) are KEPT — they appear in the final UI with `specQty: 0`
- Output: `bid_items[]` — the canonical room names for the whole job come from here

### Step 2 — Scrape Spec Book
- Extract specbook ID and token from URL
- Authenticate with specbooks-api.specbooks.cloud
- Fetch all categories (rooms) and their items — MUST paginate ALL pages (previous runs missed last sections — `last_page` from meta response must be followed to completion)
- Download each item's image from assets.specbooks.cloud → saved to `{output_dir}/spec_images/`
- Output: `spec_items[]` with room, name, model, qty, image_url (local path after download)
- If auth fails (expired token): surface a CLEAR error with instructions, do not silently return 0 items

### Step 3 — Extract Plan Images
- Convert each page of plans.pdf to a JPG image → saved to `{output_dir}/plan_images/plan-XX.jpg`
- Use pdftotext + keyword matching to detect which floor each page belongs to (basement / main / upper)
- Output: `rooms` dict — `{basement: [room names...], main: [...], upper: [...]}` + `planNavigation` with page numbers and image paths per floor

### Step 4 — Extract Cabinet Images
- Convert each page of cabinets.pdf to a PNG image → saved to `{output_dir}/cabinet_images/page-XX.png`
- Use pdftotext + keyword matching to detect which room each cabinet page belongs to
- Output: `cabinet_map` dict — `{room_name: [page_numbers]}`

### Step 5 — AI Room Mapping
- The spec book uses its own room names (MASTER BATH, KITCHEN, BATH 2, etc.)
- The bid sheet uses different room names (Master Bedroom, Main floor, Bathroom 2, etc.)
- Use Gemini to match spec room names → bid room names
- Bid sheet room names are the CANONICAL names used in the final output
- Use plans text as a tiebreaker if the mapping is ambiguous (same room, different name)
- Output: `room_map` dict — `{spec_room_name: bid_room_name}`
- Human review: any spec room that couldn't be mapped is flagged in the log

### Step 6 — AI Item Matching
- For each bid item in each room, find the matching spec item(s) in the same mapped room
- Use Gemini 2.5 Flash with retry (up to 3x on 503 / rate limit)
- Billing rules the LLM must follow:
  - "Lav" → faucet/widespread (NOT the sink bowl — that's a sub-item)
  - "Shower" → showerhead or raincan (NOT valve, trim, handle, diverter — those are sub-items)
  - "Tub/Shower" → showerhead as PRIMARY (bathtub is sub-item)
  - "Shower (2nd Head)" / "Slide Bar" → slide bar or hand shower wand
  - "Tub (freestanding)" → soaking tub or roman tub faucet
  - "Steam Shower" → steam generator
  - "Sink (Kitchen)" → kitchen faucet or prep faucet
  - "Drinking Fountain" → bottle filling station
- PRIMARY billable spec item goes FIRST in `spec_items[]`
- Supporting components (valve rough, trim, handle kit, drain, sink bowl, arm) go AFTER as sub-items
- Bid items with NO spec match (Water Heater, Floor Drain, Sump Pump, etc.) → `spec_items: []`, status: "ok"
- Spec items with NO bid match → appear in output as separate entry with `bidQty: 0`, status: "pending"
- Confidence < 0.85 → item goes to review queue (still appears in output, flagged)

### Step 7 — Generate Output
- Combine everything into the `JOB_DATA` structure (matching data.js.backup format exactly)
- Group items by bid room
- Each item: `name, bidQty, specQty, specImage (local path), specDesc, status, subItems[]`
- Status logic:
  - `"match"` (green) — bid_qty == spec_qty
  - `"missing_from_bid"` (red) — spec_qty > bid_qty (bid is MISSING something — most critical)
  - `"extra_in_bid"` (yellow) — bid_qty > spec_qty (bid has MORE than spec)
  - `"ok"` — bid-only item (Water Heater etc.), specQty: 0, NOT a discrepancy
- Each room: `name, items[], cabinetPages[], cabinetImages[], floor`
- Write to `{output_dir}/data.js` as `const JOB_DATA = {...};`
- Also write `BILLABLE_ITEMS` and `HIDE_ITEMS` constants to same file

---

## 4. Output / Deliverable

```
{output_dir}/
├── data.js                      ← JOB_DATA + BILLABLE_ITEMS + HIDE_ITEMS
├── spec_images/                 ← Downloaded from specbooks.com assets
│   ├── Brizo - Odin Semi-Pro Kitchen Faucet - 63375LF-GLLHP.jpg
│   └── ...
├── plan_images/                 ← Extracted from plans.pdf
│   ├── plan-01.jpg
│   └── ...
└── cabinet_images/              ← Extracted from cabinets.pdf
    ├── page-01.png
    └── ...
```

For multi-job (Phase 2): output goes to `{fieldcheck_dir}/jobs/{job_id}/` and is uploaded to Supabase `projects` table.

---

## 5. External Services / APIs

| Service | Purpose | Free? | Auth |
|---------|---------|-------|------|
| specbooks-api.specbooks.cloud | Fetch spec items + images | Requires client token | JWT via token in URL |
| assets.specbooks.cloud | Download spec images | Public CDN | None |
| Google Gemini 2.0 Flash | Room mapping + item matching | Free tier | GOOGLE_API_KEY |
| pdftotext (system) | Extract text from plan/cabinet PDFs | Free | None |
| pdftoppm / pdf2image | Convert PDF pages to images | Free | None |

---

## 6. Logic Branches (If/Then)

- If spec scraper returns 0 items → abort with clear error ("token may be expired — re-open URL")
- If bid item has no spec match in its room → include with `specQty: 0`, `status: "ok"` (not a discrepancy)
- If spec item has no bid match → include with `bidQty: 0`, `status: "pending"` (IS a discrepancy)
- If spec qty ≠ bid qty → `status: "pending"` (IS a discrepancy)
- If room mapping is ambiguous → log warning, attempt best-guess, flag for human review
- If Gemini returns 503 → retry up to 3x with exponential backoff, then fall back to empty match

---

## 7. Error Handling

| Failure | Response |
|---------|----------|
| Expired specbooks token | Abort Step 2, print: "Token expired. Re-open the spec URL in a browser." |
| Gemini 503 | Retry 3x with 2s/4s/8s backoff. If still failing, use empty match + flag in review queue. |
| PDF text extraction empty | Log warning "PDF may be image-based", continue with empty room/floor detection |
| XLSX column not found | Log warning, fall back to Gemini column detection. If still fails, abort with clear error. |
| Image download fails | Log warning, continue with empty image_url — don't abort the whole run |

---

## 8. Success Metric

**How do we know it worked?**
- `data.js` is written with valid JOB_DATA
- All bid items from the CSV appear somewhere in `JOB_DATA.rooms[].items[]`
- Items with matching spec entries show `specImage` (not null)
- True discrepancies (spec item with no bid match) show `status: "pending"`
- Bid-only items (Water Heater, etc.) show `status: "ok"`, `specQty: 0`
- `spec_images/`, `plan_images/`, `cabinet_images/` all populated
- `uv run pytest projects/hobble-creek-plumbing/tests/ -v` — all pass

---

## 9. Chunks (Build Plan)

- [x] Chunk 1: `parse_bid.py` — parse bid sheet → bid_items (DONE, 8 tests passing)
- [x] Chunk 2: `scrape_spec.py` — specbooks.com API scraper + image download (DONE, 10 tests passing)
- [ ] Chunk 3: `extract_plans.py` — PDF → floor/room mapping + plan page images
- [ ] Chunk 4: `extract_cabinets.py` — PDF → cabinet page → room mapping + cabinet images
- [ ] Chunk 5: `map_rooms.py` — AI room name reconciliation (spec → bid)
- [ ] Chunk 6: `match_items.py` — Gemini item matching with billing rules + retry
- [ ] Chunk 7: `generate_output.py` — assemble JOB_DATA matching data.js.backup format
- [ ] Chunk 8: `graph.py` — wire all nodes into LangGraph, CLI entry point

---

## Status
- [x] Blueprint approved by Brighton (2026-03-20)
- [ ] All chunks built and tested
- [ ] Delivered to client
