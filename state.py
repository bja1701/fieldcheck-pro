"""
State schema for FieldCheck Pro LangGraph workflow.
Passed between every node — only update the keys you change.
"""
from __future__ import annotations
from typing import Annotated, TypedDict
import operator


class FieldCheckState(TypedDict):
    # ── Inputs (required at invocation) ──────────────────────────────────────
    spec_url: str           # specbooks.com URL with token param
    bid_path: str           # path to bid sheet CSV or XLSX
    plans_path: str         # path to house plans PDF
    cabinets_path: str      # path to cabinet drawings PDF
    job_name: str           # human-readable project name (e.g. "Baker Residence")
    output_dir: str         # directory for all output files (images, data.js)
    project_id: str         # Supabase projects.id — optional; publish skipped if blank

    # ── Intermediate: parsed inputs ──────────────────────────────────────────
    bid_items: list[dict]
    # Each: {room, name, bid_qty, unit_price}

    spec_items: list[dict]
    # Each: {room, name, model, qty, image_url}

    rooms: dict
    # {rooms: {basement:[...], main:[...], upper:[...]}, planNavigation: {...}}

    cabinet_map: dict
    # {room_name: [page_numbers]}

    # ── Intermediate: matching ────────────────────────────────────────────────
    room_map: dict
    # {spec_room_name: bid_room_name} — produced by map_rooms node

    matched_items: list[dict]
    # Each: {room, bid_name, bid_qty, unit_price, spec_items:[...], confidence, notes}

    review_queue: list[dict]
    # Low-confidence matches needing human review (same schema as matched_items)

    # ── Output ────────────────────────────────────────────────────────────────
    discrepancies: list[dict]
    # Each: {room, floor, bid_name, bid_qty, spec_qty, status, spec_items, image_url}
    # status: "match" | "extra_in_bid" | "missing_from_bid" | "bid_only" | "spec_only"

    output_data: dict
    # Final structured dict ready for the frontend (replaces data.js)

    # ── Logs ─────────────────────────────────────────────────────────────────
    logs: Annotated[list[str], operator.add]
    error: str
