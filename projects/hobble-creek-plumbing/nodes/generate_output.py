"""
Node 7: generate_output
Assembles the JOB_DATA structure from all prior nodes and writes data.js.

Output state keys updated:
  output_data: the full JOB_DATA dict (also written to {output_dir}/data.js)
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from state import FieldCheckState

# ── Job-specific floor hints ─────────────────────────────────────────────────
# Numbered bathrooms can't be floor-detected from plan text alone — list them
# explicitly. Keys are bid room names, lowercased.
_ROOM_FLOOR_HINTS: dict[str, str] = {
    "bathroom 3": "upper",
    "bathroom 4": "upper",
    "bathroom 5": "basement",
}

# ── Static constants (from data.js.backup) ───────────────────────────────────

BILLABLE_ITEMS = [
    "Toilet", "Lav", "Shower", "Shower (2nd Head)", "Tub/Shower",
    "Tub (freestanding)", "Sink/Laundry", "Sink (Kitchen)", "Washer Box",
    "Hose Bib", "Hot/Cold Hose Bib", "Drinking Fountain", "Steam Shower",
    "Adventure sink", "recir. Pump with loop", "Indirect water heater",
    "Water Softener/Basic", "Future Fixtures", "Water heater/Tankless",
    "Sink/Garage", "sink/Outdoor", "Pool utilities", "Bottle filler/inwall",
    "Water Heater/powervent", "Humidifier water supply",
    "Single Grinder sewer pump", "Duel Grinder sewer pump", "Cold Plunge",
    "Floor Drain", "Roof Drains", "Water softner/whole house filter", "Urinal",
]

HIDE_ITEMS = [
    "Refridgerator Water-Line",
    "Ice bin hook up",
    "Misc. Sink (Laundry/Wet Bar/Shop)",
]

# Items sourced from architectural plans (not spec books).
# These are billable fixtures confirmed from plans — never compared to spec book.
# The frontend uses this to show them with a "from plans" badge instead of a mismatch flag.
PLAN_SOURCED_ITEMS = [
    "Hose Bib",
    "Hot/Cold Hose Bib",
    "Washer Box",
    "Ice bin hook up",
    "Refridgerator Water-Line",
    "Dog Wash",
]

_IS_BILLABLE_JS = """\
function isBillableItem(itemName) {
  const normalized = itemName.toLowerCase().trim();
  return BILLABLE_ITEMS.some(billable =>
    normalized.includes(billable.toLowerCase()) ||
    (billable === 'Lav' && (normalized.includes('lav') || normalized.includes('laboratory'))) ||
    (billable === 'Shower (2nd Head)' && (normalized.includes('2nd') || normalized.includes('second') || normalized.includes('slide'))) ||
    (billable === 'Sink (Kitchen)' && (normalized.includes('kitchen') && normalized.includes('sink'))) ||
    (billable === 'Sink/Laundry' && (normalized.includes('laundry') || normalized.includes('utility'))) ||
    (billable === 'Tub (freestanding)' && normalized.includes('freestanding'))
  );
}"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bid_rooms_ordered(bid_items: list[dict]) -> list[str]:
    """Return bid room names in first-seen order."""
    seen: set[str] = set()
    rooms: list[str] = []
    for item in bid_items:
        r = item.get("room", "").strip()
        if r and r not in seen:
            seen.add(r)
            rooms.append(r)
    return rooms


def _floor_for_room(bid_room: str, rooms_state: dict) -> str:
    """Determine which floor a bid room belongs to."""
    name_lower = bid_room.lower()

    # Keyword check first — prevents plan noise (e.g. "UPPER FLOOR CHANGES"
    # on a basement framing page) from overriding an unambiguous room name.
    if "upper" in name_lower or "3rd" in name_lower:
        return "upper"
    if "basement" in name_lower or "lower" in name_lower:
        return "basement"

    # Job-specific overrides for rooms that can't be auto-detected from plan text
    if name_lower in _ROOM_FLOOR_HINTS:
        return _ROOM_FLOOR_HINTS[name_lower]

    # For ambiguous rooms (numbered bathrooms, master bedroom, etc.), try
    # word-boundary match against plan-extracted room names.
    rooms_by_floor = (rooms_state or {}).get("rooms", {})
    for floor, room_names in rooms_by_floor.items():
        for r in (room_names or []):
            r_lower = r.lower().strip()
            if len(r_lower) < 5:
                continue
            if (re.search(r"\b" + re.escape(r_lower) + r"\b", name_lower) or
                    re.search(r"\b" + re.escape(name_lower) + r"\b", r_lower)):
                return floor

    return "main"


def _cabinet_pages_for_room(
    bid_room: str,
    cabinet_map: dict,
    room_map: dict,
) -> list[int]:
    """Return sorted page numbers for a bid room's cabinet drawings."""
    pages: list[int] = []
    bid_room_lower = bid_room.lower()
    for cabinet_room, room_pages in cabinet_map.items():
        bid = room_map.get(cabinet_room) or room_map.get(cabinet_room.upper()) or cabinet_room
        if bid.lower() == bid_room_lower:
            pages.extend(room_pages)
    return sorted(set(pages))


def _compute_status(bid_qty: int, spec_qty: int) -> str:
    if bid_qty > 0 and spec_qty == 0:
        return "ok"
    if bid_qty == 0:
        return "pending"
    if bid_qty == spec_qty:
        return "match"
    if bid_qty > spec_qty:
        return "extra_in_bid"
    return "missing_from_bid"


def _build_item(matched: dict) -> dict:
    """Convert a matched_item entry to JOB_DATA item format."""
    spec_items = matched.get("spec_items", [])
    primary = next((s for s in spec_items if s.get("is_primary")), None)
    subs = [s for s in spec_items if not s.get("is_primary")]

    bid_qty = matched.get("bid_qty", 0)
    spec_qty = int(primary["qty"]) if primary and primary.get("qty") else 0
    spec_image = primary.get("image_url") if primary else None
    spec_desc = primary.get("name", "") if primary else ""

    item: dict = {
        "name": matched["bid_name"],
        "bidQty": bid_qty,
        "specQty": spec_qty,
        "specImage": spec_image,
        "specDesc": spec_desc,
        "status": _compute_status(bid_qty, spec_qty),
    }
    if subs:
        item["subItems"] = [
            {
                "name": s.get("name", ""),
                "model": s.get("model", ""),
                "img": s.get("image_url", ""),
            }
            for s in subs
        ]
    return item


def _write_data_js(output_dir: str, job_data: dict) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    billable_js = json.dumps(BILLABLE_ITEMS, indent=2)
    hide_js = json.dumps(HIDE_ITEMS, indent=2)
    plan_sourced_js = json.dumps(PLAN_SOURCED_ITEMS, indent=2)
    job_js = json.dumps(job_data, indent=2)

    content = (
        "// Master list of billable items (items with non-zero prices)\n"
        f"const BILLABLE_ITEMS = {billable_js};\n\n"
        "// Items to hide ($0 noise from CSV)\n"
        f"const HIDE_ITEMS = {hide_js};\n\n"
        "// Items sourced from architectural plans (not spec books) — show with 'from plans' badge\n"
        f"const PLAN_SOURCED_ITEMS = {plan_sourced_js};\n\n"
        f"{_IS_BILLABLE_JS}\n\n"
        f"const JOB_DATA = {job_js};\n"
    )
    (out / "data.js").write_text(content)


# ── Main node ─────────────────────────────────────────────────────────────────

def generate_output(state: FieldCheckState) -> dict:
    matched_items = state.get("matched_items", [])
    bid_items = state.get("bid_items", [])
    spec_items = state.get("spec_items", [])
    rooms_state = state.get("rooms", {})
    cabinet_map = state.get("cabinet_map", {})
    room_map = state.get("room_map", {})
    job_name = state.get("job_name", "")
    output_dir = state.get("output_dir", "")
    spec_url = state.get("spec_url", "")

    if not matched_items:
        return {
            "error": "generate_output: no matched_items — run match_items first",
            "output_data": {},
        }

    # Group matched items by room
    items_by_room: dict[str, list[dict]] = defaultdict(list)
    for m in matched_items:
        items_by_room[m["room"]].append(m)

    # Build rooms in bid-sheet order
    room_order = _bid_rooms_ordered(bid_items)
    # Include any rooms that appear in matched_items but not in bid (spec_only rooms)
    for room in items_by_room:
        if room not in room_order:
            room_order.append(room)

    rooms_out: list[dict] = []
    for bid_room in room_order:
        room_items = items_by_room.get(bid_room, [])
        if not room_items:
            continue

        # Deduplicate by bid_name — parse_bid can produce repeated rows from
        # multi-section XLSM sheets; keep first occurrence per name.
        _seen_names: set[str] = set()
        deduped: list[dict] = []
        for it in room_items:
            if it.get("bid_name") not in _seen_names:
                _seen_names.add(it["bid_name"])
                deduped.append(it)
        room_items = deduped

        pages = _cabinet_pages_for_room(bid_room, cabinet_map, room_map)
        cabinet_images = [f"cabinet_images/page-{p:02d}.png" for p in pages]
        floor = _floor_for_room(bid_room, rooms_state)

        rooms_out.append({
            "name": bid_room,
            "items": [_build_item(m) for m in room_items],
            "cabinetPages": pages,
            "cabinetImages": cabinet_images,
            "floor": floor,
        })

    plan_nav = (rooms_state or {}).get("planNavigation", {})

    # Build specCatalog: room → list of spec items for correction modal
    spec_catalog: dict[str, list[dict]] = defaultdict(list)
    for s in spec_items:
        room = s.get("room", "").strip()
        if room:
            spec_catalog[room].append({
                "name": s.get("name", ""),
                "model": s.get("model", ""),
                "image_url": s.get("image_url", ""),
            })

    job_data: dict = {
        "project": job_name,
        "rooms": rooms_out,
        "planNavigation": plan_nav,
        "specCatalog": dict(spec_catalog),
        "specUrl": spec_url,
    }

    if output_dir:
        _write_data_js(output_dir, job_data)

    logs = [
        f"generate_output: {len(rooms_out)} rooms, "
        f"{sum(len(r['items']) for r in rooms_out)} items written"
    ]
    if output_dir:
        logs.append(f"generate_output: wrote {output_dir}/data.js")

    return {"output_data": job_data, "logs": logs}
