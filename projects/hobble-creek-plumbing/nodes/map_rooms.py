"""
Node 5: map_rooms
Uses Gemini AI to map spec book room names → bid sheet room names.

Reads raw spec room names from scrape_spec's cache file, reads bid room
names from bid_items, and calls Gemini to produce a mapping dict.

Output state keys updated:
  room_map: {spec_room_name: bid_room_name}
  e.g. {"MASTER BATH": "Master Bedroom", "KITCHEN": "Main floor", ...}

Special case: "TOILETS" (or any spec room containing only toilet items) maps
to "__TOILETS__", which match_items.py distributes across rooms.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

from state import FieldCheckState

CACHE_DIR = Path("projects/hobble-creek-plumbing/cache")


def _spec_id_from_url(url: str) -> str:
    m = re.search(r"/especbook/(\d+)", url)
    if not m:
        raise ValueError(f"Cannot find specbook ID in URL: {url}")
    return m.group(1)


def _load_spec_rooms(spec_id: str, cache_dir: Path = CACHE_DIR) -> list[str]:
    try:
        text = (cache_dir / f"raw_{spec_id}.json").read_text()
    except FileNotFoundError:
        return []
    return list(json.loads(text).keys())


def _bid_rooms(bid_items: list[dict]) -> list[str]:
    """Return deduplicated bid room names in first-seen order."""
    seen: set[str] = set()
    rooms: list[str] = []
    for item in bid_items:
        r = item.get("room", "").strip()
        if r and r not in seen:
            seen.add(r)
            rooms.append(r)
    return rooms


def _call_gemini(spec_rooms: list[str], bid_rooms: list[str], plans_context: str = "", cabinet_rooms: list[str] | None = None) -> dict[str, str | None]:
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    llm = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=os.environ.get("GOOGLE_API_KEY", ""),
        temperature=0,
    )

    context_block = ""
    if plans_context:
        context_block = f"\nHOUSE PLANS CONTEXT (use for ambiguous cases):\n{plans_context[:1500]}\n"

    cab_block = ""
    if cabinet_rooms:
        cab_block = f"\nCABINET DRAWING ROOM NAMES (also map these to bid rooms):\n{json.dumps(cabinet_rooms, indent=2)}\n"

    prompt = f"""You are mapping plumbing spec book room names and cabinet drawing room names to bid sheet room names.

SPEC BOOK ROOMS (to be mapped FROM):
{json.dumps(spec_rooms, indent=2)}{cab_block}
BID SHEET ROOMS (canonical names to map TO):
{json.dumps(bid_rooms, indent=2)}
{context_block}
Rules:
1. Map each spec room and cabinet room to exactly one bid room name, copied verbatim from the BID SHEET ROOMS list
2. Multiple source rooms may map to the same bid room (e.g. "KITCHEN" and "MUD ROOM" → "Main floor")
3. If the spec room is "TOILETS" or describes a toilet-only category, map it to "__TOILETS__"
4. If a room truly cannot be matched to any bid room, map it to null
5. Return ONLY a JSON object with no explanation or markdown

Output format (example):
{{"KITCHEN": "Main floor", "MASTER BATH": "Master Bedroom", "MASTER BATHROOM": "Master Bedroom", "TOILETS": "__TOILETS__"}}"""

    resp = llm.invoke([HumanMessage(content=prompt)])
    text = resp.content.strip()

    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: extract first {...} block
    m = re.search(r"\{[^{}]+\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"No JSON object found in Gemini response: {text[:300]}")
    return json.loads(m.group(0))


def map_rooms(state: FieldCheckState, cache_dir: Path = CACHE_DIR) -> dict:
    spec_url = state.get("spec_url", "")
    bid_items = state.get("bid_items", [])
    rooms = state.get("rooms", {})

    try:
        spec_id = _spec_id_from_url(spec_url)
    except ValueError as e:
        return {"error": str(e), "room_map": {}}

    spec_rooms = _load_spec_rooms(spec_id, cache_dir)
    if not spec_rooms:
        return {
            "error": f"map_rooms: no spec cache found for spec_id {spec_id!r} — run scrape_spec first",
            "room_map": {},
        }

    bid_room_list = _bid_rooms(bid_items)
    if not bid_room_list:
        return {"error": "map_rooms: no bid items — run parse_bid first", "room_map": {}}

    plans_context = ""
    rooms_dict = rooms or {}
    nav = rooms_dict.get("planNavigation", {})
    if nav:
        floor_names = rooms_dict.get("rooms", {})
        plans_context = json.dumps({floor: list(floor_names.get(floor, [])) for floor in nav})

    cabinet_map = state.get("cabinet_map", {})
    cabinet_rooms = list(cabinet_map.keys()) if cabinet_map else []

    try:
        room_map = _call_gemini(spec_rooms, bid_room_list, plans_context, cabinet_rooms)
    except Exception as e:
        return {"error": f"map_rooms: Gemini call failed: {e}", "room_map": {}}

    unmapped = [r for r, v in room_map.items() if not v]
    logs = [f"map_rooms: {len(room_map)} spec rooms mapped to bid rooms"]
    if unmapped:
        logs.append(f"map_rooms: WARNING — {len(unmapped)} spec rooms unmapped: {unmapped}")

    return {
        "room_map": room_map,
        "logs": logs,
    }
