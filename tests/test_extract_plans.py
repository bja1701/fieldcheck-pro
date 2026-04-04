"""Tests for extract_plans node."""
from __future__ import annotations
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "nodes"))

from nodes.extract_plans import extract_plans, _detect_floor, _extract_room_names
from nodes.pdf_utils import get_page_count

FIXTURE_PDF = Path("/home/frank/PAI/fieldcheck-pro/plans.pdf")
HAS_FIXTURE = FIXTURE_PDF.exists()


def _make_state(**overrides) -> dict:
    base = {
        "spec_url": "", "bid_path": "", "plans_path": str(FIXTURE_PDF),
        "cabinets_path": "", "job_name": "Test", "output_dir": "",
        "bid_items": [], "spec_items": [], "rooms": {}, "cabinet_map": {},
        "matched_items": [], "review_queue": [], "discrepancies": [],
        "output_data": {}, "logs": [], "error": "",
    }
    base.update(overrides)
    return base


# ── Unit tests (no file I/O) ─────────────────────────────────────────────────

class TestDetectFloor:
    def test_basement_high_score(self):
        assert _detect_floor("BASEMENT LEVEL FLOOR PLAN\nsome content") == "basement"

    def test_main_high_score(self):
        assert _detect_floor("MAIN LEVEL FLOOR PLAN\nsome content") == "main"

    def test_upper_high_score(self):
        assert _detect_floor("UPPER LEVEL FLOOR PLAN\nsome content") == "upper"

    def test_tiebreaker_prefers_highest(self):
        # page with main title beats basement footnote
        text = "MAIN LEVEL FLOOR PLAN\nbasement sq ft reference"
        assert _detect_floor(text) == "main"

    def test_no_keywords_returns_other(self):
        assert _detect_floor("GENERAL NOTES\nsome random text") == "other"

    def test_generic_basement_mention(self):
        # lowercase basement = 1pt, still wins if nothing else
        assert _detect_floor("basement floor drain location") == "basement"


class TestExtractRoomNames:
    def test_extracts_caps_room_names(self):
        text = "KITCHEN\n22' - 4\" x 21' - 6\"\nPANTRY\n10' - 0\""
        names = _extract_room_names(text)
        assert "KITCHEN" in names or "PANTRY" in names

    def test_filters_short_names(self):
        names = _extract_room_names("AB\nsome text")
        assert "AB" not in names

    def test_no_duplicates(self):
        text = "KITCHEN\nKITCHEN\nKITCHEN"
        names = _extract_room_names(text)
        assert names.count("KITCHEN") <= 1


# ── Integration tests (require real fixture) ─────────────────────────────────

@pytest.mark.skipif(not HAS_FIXTURE, reason="Fixture PDF not available")
class TestExtractPlansIntegration:
    def test_returns_rooms_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = extract_plans(_make_state(output_dir=tmp))
        assert "rooms" in result
        assert "rooms" in result["rooms"]
        assert "planNavigation" in result["rooms"]

    def test_rooms_has_three_floors(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = extract_plans(_make_state(output_dir=tmp))
        nav = result["rooms"]["rooms"]
        assert "basement" in nav
        assert "main" in nav
        assert "upper" in nav

    def test_floor_assignments_correct(self):
        """Baker plans.pdf page 4 = basement, page 6 = main, page 8 = upper."""
        with tempfile.TemporaryDirectory() as tmp:
            result = extract_plans(_make_state(output_dir=tmp))
        nav = result["rooms"]["planNavigation"]
        assert 4 in nav["basement"]["pages"], f"Expected pg 4 in basement, got {nav['basement']['pages']}"
        assert 6 in nav["main"]["pages"], f"Expected pg 6 in main, got {nav['main']['pages']}"
        assert 8 in nav["upper"]["pages"], f"Expected pg 8 in upper, got {nav['upper']['pages']}"

    def test_images_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = extract_plans(_make_state(output_dir=tmp))
        assert "rooms" in result
        nav = result["rooms"]["planNavigation"]
        all_images = (
            nav["basement"]["images"]
            + nav["main"]["images"]
            + nav["upper"]["images"]
            + nav.get("other", {}).get("images", [])
        )
        assert len(all_images) > 0

    def test_logs_populated(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = extract_plans(_make_state(output_dir=tmp))
        assert result.get("logs")
        assert "extract_plans" in result["logs"][0]

    def test_missing_file_returns_error(self):
        result = extract_plans(_make_state(plans_path="/nonexistent/plans.pdf"))
        assert "error" in result
        assert result["error"]

    def test_plan_navigation_images_relative_paths(self):
        """Image paths must be relative (plan_images/plan-NN.jpg), not absolute."""
        with tempfile.TemporaryDirectory() as tmp:
            result = extract_plans(_make_state(output_dir=tmp))
        nav = result["rooms"]["planNavigation"]
        for floor in ["basement", "main", "upper"]:
            for img_path in nav[floor]["images"]:
                assert not img_path.startswith("/"), f"Expected relative path, got: {img_path}"
                assert img_path.startswith("plan_images/"), f"Expected plan_images/ prefix: {img_path}"

    def test_page_count_matches_navigation(self):
        """Total pages across all floors must equal PDF page count."""
        with tempfile.TemporaryDirectory() as tmp:
            result = extract_plans(_make_state(output_dir=tmp))
        page_count = get_page_count(str(FIXTURE_PDF))
        nav = result["rooms"]["planNavigation"]
        total = sum(len(nav[f]["pages"]) for f in nav)
        assert total == page_count, f"Expected {page_count} total pages, got {total}"
