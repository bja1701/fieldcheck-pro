"""Tests for extract_cabinets node."""
from __future__ import annotations
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "nodes"))

from nodes.extract_cabinets import extract_cabinets, _extract_room

FIXTURE_PDF = Path("/home/frank/PAI/fieldcheck-pro/cabinets.pdf")
HAS_FIXTURE = FIXTURE_PDF.exists()


def _make_state(**overrides) -> dict:
    base = {
        "spec_url": "", "bid_path": "", "plans_path": "",
        "cabinets_path": str(FIXTURE_PDF), "job_name": "Test", "output_dir": "",
        "bid_items": [], "spec_items": [], "rooms": {}, "cabinet_map": {},
        "matched_items": [], "review_queue": [], "discrepancies": [],
        "output_data": {}, "logs": [], "error": "",
    }
    base.update(overrides)
    return base


# ── Unit tests ───────────────────────────────────────────────────────────────

class TestExtractRoom:
    def test_extracts_room_between_client_and_date(self):
        text = "Client: MILLHAVEN HOMES\nKITCHEN\nDate: 11/07/25\n"
        assert _extract_room(text) == "KITCHEN"

    def test_extracts_multi_word_room(self):
        text = "Client: MILLHAVEN HOMES\nMASTER BATHROOM\nDate: 11/07/25\n"
        assert _extract_room(text) == "MASTER BATHROOM"

    def test_returns_none_when_no_header(self):
        text = "172\n86\n32\n6\n25\n"
        assert _extract_room(text) is None

    def test_strips_whitespace(self):
        text = "Client: MILLHAVEN HOMES\n  BATHROOM 2  \nDate: 11/07/25\n"
        assert _extract_room(text) == "BATHROOM 2"

    def test_header_buried_in_dimensions(self):
        """Room header can appear after dimension data on the same page."""
        text = "150\n25\nClient: MILLHAVEN HOMES\nBUTLERS PANTRY\nDate: 11/07/25\nApproved by:\n"
        assert _extract_room(text) == "BUTLERS PANTRY"


# ── Integration tests ────────────────────────────────────────────────────────

@pytest.mark.skipif(not HAS_FIXTURE, reason="Fixture PDF not available")
class TestExtractCabinetsIntegration:
    def test_returns_cabinet_map_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = extract_cabinets(_make_state(output_dir=tmp))
        assert "cabinet_map" in result

    def test_kitchen_maps_to_pages_1_through_8(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = extract_cabinets(_make_state(output_dir=tmp))
        cmap = result["cabinet_map"]
        assert "KITCHEN" in cmap
        assert cmap["KITCHEN"] == list(range(1, 9)), f"Expected pages 1-8, got {cmap['KITCHEN']}"

    def test_has_at_least_10_rooms(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = extract_cabinets(_make_state(output_dir=tmp))
        assert len(result["cabinet_map"]) >= 10

    def test_page_numbers_are_ints(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = extract_cabinets(_make_state(output_dir=tmp))
        for room, pages in result["cabinet_map"].items():
            for p in pages:
                assert isinstance(p, int), f"Expected int page num, got {type(p)} for room {room}"

    def test_all_30_pages_assigned(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = extract_cabinets(_make_state(output_dir=tmp))
        all_pages = [p for pages in result["cabinet_map"].values() for p in pages]
        assert sorted(all_pages) == list(range(1, 31))

    def test_png_images_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            extract_cabinets(_make_state(output_dir=tmp))
            images = list(Path(tmp, "cabinet_images").glob("page-*.png"))
        assert len(images) == 30

    def test_image_names_zero_padded(self):
        with tempfile.TemporaryDirectory() as tmp:
            extract_cabinets(_make_state(output_dir=tmp))
            names = sorted(p.name for p in Path(tmp, "cabinet_images").glob("page-*.png"))
        assert names[0] == "page-01.png"
        assert names[-1] == "page-30.png"

    def test_logs_populated(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = extract_cabinets(_make_state(output_dir=tmp))
        assert result.get("logs")
        assert "extract_cabinets" in result["logs"][0]

    def test_missing_file_returns_error(self):
        result = extract_cabinets(_make_state(cabinets_path="/nonexistent/cabinets.pdf"))
        assert "error" in result
        assert result["error"]
