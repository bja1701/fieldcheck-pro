"""
Node 4: extract_cabinets
Converts cabinet drawings PDF pages to PNG images and maps each page to a room.

Every page has a "Client: ... / ROOM NAME / Date: ..." header — room name is the
line between "Client:" and "Date:". Pages missing the header carry forward the
previous page's room (fallback for unusual formats).

Output state keys updated:
  cabinet_map: {room_name: [page_numbers]}
  e.g. {"KITCHEN": [1,2,3,4,5,6,7,8], "BUTLERS PANTRY": [9,10,11], ...}
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from state import FieldCheckState
from nodes.pdf_utils import get_page_count, extract_all_text, convert_pdf_pages

# Matches the room name between "Client: ..." and "Date:" header lines
_CLIENT_DATE_RE = re.compile(r"Client:[^\n]+\n([^\n]+)\nDate:")


def _extract_room(text: str) -> str | None:
    """Return the room name from a page's Client/Date header, or None."""
    m = _CLIENT_DATE_RE.search(text)
    return m.group(1).strip() if m else None


def extract_cabinets(state: FieldCheckState) -> dict:
    cabinets_path = state.get("cabinets_path", "")
    output_dir = state.get("output_dir", "output")

    if not cabinets_path or not Path(cabinets_path).exists():
        return {"error": f"extract_cabinets: cabinets file not found: {cabinets_path!r}", "cabinet_map": {}}

    images_dir = Path(output_dir) / "cabinet_images"
    images_dir.mkdir(parents=True, exist_ok=True)

    try:
        page_count = get_page_count(cabinets_path)
    except Exception as e:
        return {"error": f"extract_cabinets: could not read page count: {e}", "cabinet_map": {}}

    page_texts = extract_all_text(cabinets_path, page_count)

    # Map each page to a room, carrying forward if header not found
    cabinet_map: dict[str, list[int]] = defaultdict(list)
    current_room = "UNKNOWN"
    unknown_pages: list[int] = []

    for page_num in range(1, page_count + 1):
        room = _extract_room(page_texts[page_num])
        if room:
            current_room = room
        elif current_room == "UNKNOWN":
            unknown_pages.append(page_num)
        cabinet_map[current_room].append(page_num)

    logs = [f"extract_cabinets: {page_count} pages, {len(cabinet_map)} rooms"]
    if unknown_pages:
        logs.append(f"extract_cabinets: WARNING — {len(unknown_pages)} pages with no room header (carry-forward failed): {unknown_pages}")

    # Convert all pages to PNG images
    try:
        convert_pdf_pages(cabinets_path, images_dir, page_count, "png", "page-", "cabinet_images")
    except Exception as e:
        return {"error": f"extract_cabinets: image conversion failed: {e}", "cabinet_map": dict(cabinet_map)}

    return {
        "cabinet_map": dict(cabinet_map),
        "logs": logs,
    }
