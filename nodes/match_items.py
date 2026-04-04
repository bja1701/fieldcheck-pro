"""
Node 6: match_items
Uses Gemini AI to match each bid item to its corresponding spec book item(s).

One Gemini call per room (batch matching). Billing rules in the prompt direct
Gemini to choose the PRIMARY billable spec item (e.g., Lav → faucet, not sink
bowl) with supporting sub-items listed after.

Spec items not matched to any bid item are added as spec_only entries
(bid_qty: 0). Confirmed matches from confirmed_matches.json skip Gemini.

Output state keys updated:
  matched_items: list of match dicts (all rooms combined)
  review_queue:  subset of matched_items where confidence < 0.85
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

from state import FieldCheckState

CONFIRMED_MATCHES_PATH = Path("projects/hobble-creek-plumbing/confirmed_matches.json")
CONFIDENCE_THRESHOLD = 0.85
SPEC_ONLY_NOTE = "spec_only"
PLAN_SOURCED_NOTE = "plan_sourced"

# Items that come from architectural plans (not spec books).
# Never compare against spec book — skip Gemini for these entirely.
PLAN_SOURCED_PATTERNS = re.compile(
    r"^(hose\s*bib|hot[/\s]*cold\s*hose\s*bib|washer\s*box|ice\s*bin|"
    r"refrigerator|refridgerator|dog\s*wash)",
    re.IGNORECASE,
)


def _is_plan_sourced(name: str) -> bool:
    """Return True if this bid item comes from plans (not spec book)."""
    return bool(PLAN_SOURCED_PATTERNS.match(name.strip()))


BILLING_RULES = """
BILLING RULES (follow exactly when choosing the PRIMARY spec item):
- "Lav"               → PRIMARY: faucet or widespread faucet (NOT sink bowl — sub-item)
- "Shower"            → PRIMARY: showerhead or raincan (NOT valve/trim/handle/diverter — sub-items)
                        Shower arm is a SUB-ITEM under Shower, NOT a standalone primary
- "Tub/Shower"        → PRIMARY: showerhead (bathtub is a sub-item)
                        Tub spout is a SUB-ITEM under Tub/Shower, NOT a standalone primary
- "Shower (2nd Head)" → PRIMARY: slide bar or hand shower wand
- "Slide Bar"         → PRIMARY: slide bar or hand shower wand
                        Hand shower outlet is a SUB-ITEM under Slide Bar, NOT standalone
- "Tub (freestanding)"→ PRIMARY: soaking tub or roman tub faucet
                        Tub spout is a SUB-ITEM here too
- "Steam Shower"      → PRIMARY: steam generator
- "Sink (Kitchen)"    → PRIMARY: kitchen faucet or prep faucet
- "Drinking Fountain" → PRIMARY: bottle filling station
- "Toilet"            → PRIMARY: the toilet itself
- "Hose Bib"          → PRIMARY: hose bib or outdoor faucet
- "Urinal"            → PRIMARY: the urinal fixture itself (Toto, American Standard, Kohler, etc.)
                        Match ANY spec item with "urinal" in its name — even from a different room section
- Sub-items (valve rough, trim kit, handle kit, drain, sink bowl, faucet arm, flush valve,
             shower arm, tub spout, hand shower outlet, rough-in valve) come AFTER primary
- Rough-in valves are always sub-items — never match a bid item to a rough-in valve as primary
"""


def _group_by_room(items: list[dict]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        result[item.get("room", "")].append(item)
    return result


def _load_confirmed(path: Path = CONFIRMED_MATCHES_PATH) -> dict:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}


def _spec_key(spec: dict, idx: int) -> str:
    """Unique key for a spec item — model if present, else name. idx is fallback if name also missing."""
    return spec.get("model", "") or f"__name_{spec.get('name', idx)}"


def _call_gemini_for_room(
    bid_items: list[dict],
    spec_items: list[dict],
    llm: ChatGoogleGenerativeAI,
) -> list[dict]:
    """One Gemini call for all bid items in a room. Returns parsed match list."""
    indexed_specs = [
        {
            "index": i,
            "name": s["name"],
            "model": s.get("model", ""),
            "qty": s.get("qty", 1),
        }
        for i, s in enumerate(spec_items)
    ]
    bid_list = [
        {"bid_name": b["name"], "bid_qty": b.get("bid_qty", 1)}
        for b in bid_items
    ]

    prompt = f"""You are matching plumbing bid items to spec book items for a bid verification system.

BID ITEMS to match:
{json.dumps(bid_list, indent=2)}

AVAILABLE SPEC ITEMS (reference by index):
{json.dumps(indexed_specs, indent=2)}
{BILLING_RULES}
For each bid item return:
- primary_spec_index: index of the PRIMARY billable spec item (null if no match)
- sub_spec_indices: list of supporting component indices (may be empty)
- confidence: 0.0 to 1.0
- notes: brief explanation

Return ONLY a JSON array, no explanation or markdown:
[
  {{
    "bid_name": "Lav",
    "primary_spec_index": 5,
    "sub_spec_indices": [8, 12],
    "confidence": 0.95,
    "notes": "Matched widespread faucet per Lav billing rule"
  }}
]"""

    resp = llm.invoke([HumanMessage(content=prompt)])
    text = resp.content.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if not m:
            raise ValueError(f"No JSON array in Gemini response: {text[:300]}")
        return json.loads(m.group(0))


def _retry_call(fn, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            err = str(e).lower()
            if "503" in err or "rate" in err or "quota" in err:
                time.sleep(2 ** attempt * 2)  # 2s, 4s, 8s
            else:
                raise


def _fix_unmatched_urinals(matched: list[dict], all_spec_items: list[dict]) -> list[dict]:
    """Cross-room fallback: if a 'Urinal' bid item has no spec match, search all spec items.

    Scott's Meeting 2 bug: urinals appeared in spec book rooms that weren't mapped
    to the bid room containing the Urinal bid item. This fallback ensures urinals
    are always matched when a matching spec item exists anywhere in the spec book.
    """
    urinal_specs = [
        s for s in all_spec_items
        if "urinal" in s.get("name", "").lower()
    ]
    if not urinal_specs:
        return matched

    result: list[dict] = []
    for m in matched:
        if (
            m.get("bid_name", "").lower() == "urinal"
            and not m.get("spec_items")
            and m.get("notes") != SPEC_ONLY_NOTE
            and m.get("notes") != PLAN_SOURCED_NOTE
        ):
            spec = urinal_specs[0]
            result.append({
                **m,
                "spec_items": [{**spec, "is_primary": True}],
                "confidence": 0.9,
                "notes": "urinal matched via cross-room fallback",
            })
        else:
            result.append(m)
    return result


def _build_room_match(
    room: str,
    room_bid: list[dict],
    room_spec: list[dict],
    confirmed: dict,
    llm: ChatGoogleGenerativeAI,
) -> tuple[list[dict], list[dict]]:
    """Match all bid items in a room. Returns (matched_items, review_queue)."""
    used_keys: set[str] = set()
    matched: list[dict] = []
    review: list[dict] = []

    # Plan-sourced items bypass Gemini entirely — they come from plans, not spec books.
    # Add them directly with no spec match and a "plan_sourced" note.
    plan_sourced_bid: list[dict] = []
    spec_matched_bid: list[dict] = []
    for bid in room_bid:
        if _is_plan_sourced(bid["name"]):
            plan_sourced_bid.append(bid)
        else:
            spec_matched_bid.append(bid)

    for bid in plan_sourced_bid:
        matched.append({
            "room": room,
            "bid_name": bid["name"],
            "bid_qty": bid.get("bid_qty", 1),
            "unit_price": bid.get("unit_price"),
            "spec_items": [],
            "confidence": 1.0,
            "notes": PLAN_SOURCED_NOTE,
        })

    # Confirmed matches
    unconfirmed_bid: list[dict] = []
    for bid in spec_matched_bid:
        key = f"{room}:{bid['name']}"
        if key in confirmed:
            c = confirmed[key]
            primary_model = c.get("primary_model", "")
            sub_models = set(c.get("sub_models", []))
            spec_refs: list[dict] = []
            for spec in room_spec:
                sk = _spec_key(spec, -1)
                if sk == primary_model:
                    used_keys.add(sk)
                    spec_refs.insert(0, {**spec, "is_primary": True})
                elif sk in sub_models:
                    used_keys.add(sk)
                    spec_refs.append({**spec, "is_primary": False})
            matched.append({
                "room": room,
                "bid_name": bid["name"],
                "bid_qty": bid.get("bid_qty", 1),
                "unit_price": bid.get("unit_price"),
                "spec_items": spec_refs,
                "confidence": c.get("confidence", 1.0),
                "notes": c.get("notes", "confirmed"),
            })
        else:
            unconfirmed_bid.append(bid)

    # Deduplicate by name — parse_bid can produce duplicate rows from repeated
    # XLSM sections; keep last occurrence (consistent with bid_by_name dict)
    _seen: dict[str, dict] = {}
    for b in unconfirmed_bid:
        _seen[b["name"]] = b
    unconfirmed_bid = list(_seen.values())

    # Gemini matching
    if unconfirmed_bid:
        if room_spec:
            gemini_matches = _retry_call(
                lambda: _call_gemini_for_room(unconfirmed_bid, room_spec, llm)
            )
        else:
            gemini_matches = [
                {
                    "bid_name": b["name"],
                    "primary_spec_index": None,
                    "sub_spec_indices": [],
                    "confidence": 1.0,
                    "notes": "no spec items in room",
                }
                for b in unconfirmed_bid
            ]

        bid_by_name = {b["name"]: b for b in unconfirmed_bid}
        for gm in gemini_matches:
            bid = bid_by_name.get(gm["bid_name"])
            if not bid:
                continue

            spec_refs = []
            pi = gm.get("primary_spec_index")
            if pi is not None:
                pi_int = int(pi)
                if 0 <= pi_int < len(room_spec):
                    s = room_spec[pi_int]
                    used_keys.add(_spec_key(s, pi_int))
                    spec_refs.append({**s, "is_primary": True})

            for si in gm.get("sub_spec_indices") or []:
                si_int = int(si)
                if 0 <= si_int < len(room_spec):
                    s = room_spec[si_int]
                    used_keys.add(_spec_key(s, si_int))
                    spec_refs.append({**s, "is_primary": False})

            entry = {
                "room": room,
                "bid_name": bid["name"],
                "bid_qty": bid.get("bid_qty", 1),
                "unit_price": bid.get("unit_price"),
                "spec_items": spec_refs,
                "confidence": float(gm.get("confidence", 0.0)),
                "notes": gm.get("notes", ""),
            }
            matched.append(entry)
            if entry["confidence"] < CONFIDENCE_THRESHOLD:
                review.append(entry)

    # Spec-only items
    for i, spec in enumerate(room_spec):
        if _spec_key(spec, i) not in used_keys:
            matched.append({
                "room": room,
                "bid_name": spec["name"],
                "bid_qty": 0,
                "unit_price": None,
                "spec_items": [{**spec, "is_primary": True}],
                "confidence": 1.0,
                "notes": SPEC_ONLY_NOTE,
            })

    return matched, review


def match_items(state: FieldCheckState) -> dict:
    bid_items = state.get("bid_items", [])
    spec_items = state.get("spec_items", [])
    room_map = state.get("room_map", {})

    if not bid_items:
        return {
            "error": "match_items: no bid items — run parse_bid first",
            "matched_items": [],
            "review_queue": [],
        }

    # Apply room_map translation: spec items stored with raw spec room names
    # (those not in scrape_spec's hardcoded ROOM_MAP) get translated to bid room names.
    # Items already carrying a bid room name are left unchanged.
    if room_map:
        remapped: list[dict] = []
        for item in spec_items:
            raw = item["room"]
            if raw in room_map:
                bid_room = room_map[raw]
                if bid_room:  # None means genuinely unmappable — discard
                    remapped.append({**item, "room": bid_room})
            else:
                remapped.append(item)  # Already has a bid room name from ROOM_MAP
        spec_items = remapped

    confirmed = _load_confirmed()
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    llm = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=os.environ.get("GOOGLE_API_KEY", ""),
        temperature=0,
    )

    bid_by_room = _group_by_room(bid_items)
    spec_by_room = _group_by_room(spec_items)

    all_matched: list[dict] = []
    all_review: list[dict] = []

    for room in sorted(set(bid_by_room) | set(spec_by_room)):
        try:
            room_matched, room_review = _build_room_match(
                room,
                bid_by_room.get(room, []),
                spec_by_room.get(room, []),
                confirmed,
                llm,
            )
        except Exception as e:
            return {
                "error": f"match_items: failed for room {room!r}: {e}",
                "matched_items": all_matched,
                "review_queue": all_review,
            }
        all_matched.extend(room_matched)
        all_review.extend(room_review)

    # Cross-room urinal fallback: fix unmatched "Urinal" bid items using any
    # urinal spec item in the spec book (urinals are often in unmapped rooms).
    all_matched = _fix_unmatched_urinals(all_matched, spec_items)

    spec_only_count = sum(1 for m in all_matched if m["notes"] == SPEC_ONLY_NOTE)
    plan_sourced_count = sum(1 for m in all_matched if m["notes"] == PLAN_SOURCED_NOTE)
    bid_count = len(all_matched) - spec_only_count - plan_sourced_count
    logs = [
        f"match_items: {bid_count} bid matches, {spec_only_count} spec_only, "
        f"{plan_sourced_count} plan_sourced, {len(all_review)} flagged for review"
    ]

    return {
        "matched_items": all_matched,
        "review_queue": all_review,
        "logs": logs,
    }
