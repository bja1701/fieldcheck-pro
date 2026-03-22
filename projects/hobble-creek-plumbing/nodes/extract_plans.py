"""
Node 3: extract_plans
Converts house plans PDF pages to JPG images and detects which floor each page belongs to.

Output state keys updated:
  rooms: {
      rooms: {basement: [room_names...], main: [...], upper: [...]},
      planNavigation: {
          basement: {pages: [int, ...], images: ["plan_images/plan-NN.jpg", ...]},
          main:     {pages: [...], images: [...]},
          upper:    {pages: [...], images: [...]},
          other:    {pages: [...], images: [...]},
      }
  }
"""
from __future__ import annotations

import re
from pathlib import Path

from state import FieldCheckState
from nodes.pdf_utils import get_page_count, extract_all_text, convert_pdf_pages

# Floor keyword scoring: (pattern, score, floor)
_FLOOR_PATTERNS: list[tuple[str, int, str]] = [
    ("BASEMENT LEVEL FLOOR PLAN", 4, "basement"),
    ("BASEMENT LEVEL DIMENSION PLAN", 4, "basement"),
    ("BASEMENT LEVEL ELECTRICAL PLAN", 4, "basement"),
    ("BASEMENT SLAB", 3, "basement"),
    ("BASEMENT LEVEL", 3, "basement"),
    ("Basement Floor", 2, "basement"),
    ("basement", 1, "basement"),
    ("MAIN LEVEL FLOOR PLAN", 4, "main"),
    ("MAIN LEVEL DIMENSION PLAN", 4, "main"),
    ("MAIN LEVEL ELECTRICAL PLAN", 4, "main"),
    ("MAIN FLOOR FRAMING PLAN", 3, "main"),
    ("MAIN FLOOR SHEAR WALL", 3, "main"),
    ("MAIN LEVEL", 3, "main"),
    ("Main Floor", 2, "main"),
    ("main level", 1, "main"),
    ("main floor", 1, "main"),
    ("UPPER LEVEL FLOOR PLAN", 4, "upper"),
    ("UPPER LEVEL DIMENSION PLAN", 4, "upper"),
    ("UPPER LEVEL ELECTRICAL PLAN", 4, "upper"),
    ("UPPER FLOOR FRAMING PLAN", 3, "upper"),
    ("UPPER FLOOR SHEAR WALL", 3, "upper"),
    ("UPPER LEVEL", 3, "upper"),
    ("Upper Floor", 2, "upper"),
    ("upper level", 1, "upper"),
    ("upper floor", 1, "upper"),
]

# Regex to extract room-name-like strings: 2+ ALL-CAPS words (or common abbreviations)
_ROOM_NAME_RE = re.compile(r"\b([A-Z][A-Z\./&'\- ]{2,}[A-Z])\b")

# Noise phrases to exclude from room name extraction
_ROOM_NAME_NOISE = {
    "GENERAL", "KEYED NOTES", "DRAWING TITLE", "PROJECT TITLE",
    "DRAWING INDEX", "DRAWING REVISIONS", "DESCRIPTION",
    "FLOOR FINISH SCHEDULE", "GENERAL STRUCTURAL NOTES",
    "DRAWN BY", "ALL DIMENSIONS", "W.I.C", "FAU", "F.A.U", "WH",
    "MECH", "LIVING SPACE", "STORAGE", "GARAGE", "COVERED PORCH",
    "OPTIONAL STORAGE", "UNEXCAVATED", "NOTE",
}


def _detect_floor(text: str) -> str:
    """Return 'basement', 'main', 'upper', or 'other' based on keyword scoring."""
    scores: dict[str, int] = {"basement": 0, "main": 0, "upper": 0}
    for pattern, score, floor in _FLOOR_PATTERNS:
        if pattern in text:
            scores[floor] += score
    best_floor = max(scores, key=lambda f: scores[f])
    return best_floor if scores[best_floor] > 0 else "other"


def _extract_room_names(text: str) -> list[str]:
    """Extract room-name-like all-caps phrases from page text."""
    candidates = _ROOM_NAME_RE.findall(text)
    rooms = []
    seen = set()
    for c in candidates:
        name = c.strip()
        if len(name) < 4:
            continue
        if name in seen:
            continue
        if any(noise in name for noise in _ROOM_NAME_NOISE):
            continue
        if not re.search(r"[A-Z]{2}", name):
            continue
        seen.add(name)
        rooms.append(name)
    return rooms


def extract_plans(state: FieldCheckState) -> dict:
    plans_path = state.get("plans_path", "")
    output_dir = state.get("output_dir", "output")

    if not plans_path or not Path(plans_path).exists():
        return {"error": f"extract_plans: plans file not found: {plans_path!r}", "rooms": {}}

    images_dir = Path(output_dir) / "plan_images"
    images_dir.mkdir(parents=True, exist_ok=True)

    try:
        page_count = get_page_count(plans_path)
    except Exception as e:
        return {"error": f"extract_plans: could not read page count: {e}", "rooms": {}}

    page_texts = extract_all_text(plans_path, page_count)
    page_floors = {n: _detect_floor(t) for n, t in page_texts.items()}

    try:
        page_images = convert_pdf_pages(plans_path, images_dir, page_count, "jpeg", "plan-", "plan_images")
    except Exception as e:
        return {"error": f"extract_plans: image conversion failed: {e}", "rooms": {}}

    floors = ["basement", "main", "upper", "other"]
    floor_pages: dict[str, list[int]] = {f: [] for f in floors}
    floor_images: dict[str, list[str]] = {f: [] for f in floors}
    floor_room_sets: dict[str, set[str]] = {"basement": set(), "main": set(), "upper": set()}

    for page_num in range(1, page_count + 1):
        floor = page_floors[page_num]
        floor_pages[floor].append(page_num)
        if page_num in page_images:
            floor_images[floor].append(page_images[page_num])
        if floor in floor_room_sets:
            floor_room_sets[floor].update(_extract_room_names(page_texts[page_num]))

    rooms_output = {
        "rooms": {
            "basement": sorted(floor_room_sets["basement"]),
            "main":     sorted(floor_room_sets["main"]),
            "upper":    sorted(floor_room_sets["upper"]),
        },
        "planNavigation": {
            f: {"pages": floor_pages[f], "images": floor_images[f]}
            for f in floors
        },
    }

    assigned = sum(len(floor_pages[f]) for f in ["basement", "main", "upper"])
    return {
        "rooms": rooms_output,
        "logs": [f"extract_plans: {page_count} pages, {assigned} floor-assigned, {len(page_images)} images written"],
    }
