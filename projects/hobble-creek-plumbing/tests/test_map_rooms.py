"""Tests for map_rooms node."""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "nodes"))

from nodes.map_rooms import map_rooms, _spec_id_from_url, _bid_rooms, _load_spec_rooms

SPEC_ID = "3408205"
CACHE_FILE_NAME = f"raw_{SPEC_ID}.json"

SAMPLE_SPEC_ROOMS = [
    "KITCHEN", "MUD ROOM", "1/2 BATH 1", "1/2 BATH 2",
    "MASTER BATH", "GOLF SIMULATOR", "BATH 2", "BATH 3",
    "BATH 4", "UPPER LAUNDRY", "BATH 5", "REC ROOM", "TOILETS",
]

SAMPLE_BID_ROOMS = [
    "Main floor", "1/2  Bath", "Master Bedroom",
    "Basement", "Bathroom 2", "Bathroom 3",
    "Bathroom 4", "Upper Floor", "Bathroom 5",
]

SAMPLE_ROOM_MAP = {
    "KITCHEN": "Main floor",
    "MUD ROOM": "Main floor",
    "1/2 BATH 1": "1/2  Bath",
    "1/2 BATH 2": "1/2  Bath",
    "MASTER BATH": "Master Bedroom",
    "GOLF SIMULATOR": "Basement",
    "BATH 2": "Bathroom 2",
    "BATH 3": "Bathroom 3",
    "BATH 4": "Bathroom 4",
    "UPPER LAUNDRY": "Upper Floor",
    "BATH 5": "Bathroom 5",
    "REC ROOM": "Basement",
    "TOILETS": "__TOILETS__",
}


def _make_state(**overrides) -> dict:
    base = {
        "spec_url": f"https://specbooks.com/v4/especbook/{SPEC_ID}?token=abc123",
        "bid_path": "", "plans_path": "", "cabinets_path": "",
        "job_name": "Test", "output_dir": "",
        "bid_items": [{"room": r, "name": "item", "bid_qty": 1, "unit_price": None} for r in SAMPLE_BID_ROOMS],
        "spec_items": [], "rooms": {}, "cabinet_map": {}, "room_map": {},
        "matched_items": [], "review_queue": [], "discrepancies": [],
        "output_data": {}, "logs": [], "error": "",
    }
    base.update(overrides)
    return base


def _make_cache(tmp_dir: Path) -> Path:
    """Write a minimal spec cache file to tmp_dir."""
    data = {room: [{"name": "item", "qty": 1}] for room in SAMPLE_SPEC_ROOMS}
    cache_file = tmp_dir / CACHE_FILE_NAME
    cache_file.write_text(json.dumps(data))
    return tmp_dir


def _mock_llm_response(room_map: dict) -> MagicMock:
    msg = MagicMock()
    msg.content = json.dumps(room_map)
    llm = MagicMock()
    llm.invoke.return_value = msg
    return llm


# ── Unit tests ────────────────────────────────────────────────────────────────

class TestSpecIdFromUrl:
    def test_extracts_id(self):
        assert _spec_id_from_url("https://specbooks.com/v4/especbook/3408205?token=abc") == "3408205"

    def test_raises_without_especbook(self):
        with pytest.raises(ValueError, match="specbook ID"):
            _spec_id_from_url("https://specbooks.com/v4/something?token=abc")

    def test_numeric_id_preserved_as_string(self):
        result = _spec_id_from_url("https://specbooks.com/v4/especbook/9999999?token=x")
        assert result == "9999999"


class TestBidRooms:
    def test_deduplicates(self):
        items = [
            {"room": "Main floor"}, {"room": "Main floor"}, {"room": "Basement"},
        ]
        result = _bid_rooms(items)
        assert result == ["Main floor", "Basement"]

    def test_preserves_order(self):
        rooms = ["Basement", "Main floor", "Master Bedroom"]
        items = [{"room": r} for r in rooms]
        assert _bid_rooms(items) == rooms

    def test_skips_empty_room(self):
        items = [{"room": ""}, {"room": "Main floor"}]
        assert _bid_rooms(items) == ["Main floor"]


class TestLoadSpecRooms:
    def test_returns_empty_if_no_cache(self):
        result = _load_spec_rooms("9999999", Path("/nonexistent/cache"))
        assert result == []

    def test_returns_keys_from_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            data = {"KITCHEN": [], "MASTER BATH": []}
            (tmp_path / f"raw_42.json").write_text(json.dumps(data))
            result = _load_spec_rooms("42", tmp_path)
        assert "KITCHEN" in result
        assert "MASTER BATH" in result


# ── Mocked integration tests ─────────────────────────────────────────────────

class TestMapRoomsMocked:
    def _run(self, state: dict, room_map: dict) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = _make_cache(Path(tmp))
            mock_llm = _mock_llm_response(room_map)
            with patch("nodes.map_rooms.ChatGoogleGenerativeAI", return_value=mock_llm):
                return map_rooms(state, cache_dir=cache_dir)

    def test_returns_room_map_key(self):
        result = self._run(_make_state(), SAMPLE_ROOM_MAP)
        assert "room_map" in result

    def test_room_map_has_expected_mappings(self):
        result = self._run(_make_state(), SAMPLE_ROOM_MAP)
        rm = result["room_map"]
        assert rm.get("MASTER BATH") == "Master Bedroom"
        assert rm.get("KITCHEN") == "Main floor"

    def test_toilets_maps_to_special_marker(self):
        result = self._run(_make_state(), SAMPLE_ROOM_MAP)
        assert result["room_map"].get("TOILETS") == "__TOILETS__"

    def test_logs_populated(self):
        result = self._run(_make_state(), SAMPLE_ROOM_MAP)
        assert result.get("logs")
        assert any("map_rooms" in log for log in result["logs"])

    def test_logs_count_of_rooms(self):
        result = self._run(_make_state(), SAMPLE_ROOM_MAP)
        assert any(str(len(SAMPLE_ROOM_MAP)) in log for log in result["logs"])

    def test_logs_warning_for_unmapped(self):
        partial_map = {**SAMPLE_ROOM_MAP, "GOLF SIMULATOR": None}
        result = self._run(_make_state(), partial_map)
        assert any("WARNING" in log for log in result["logs"])


class TestMapRoomsErrors:
    def test_error_if_no_cache(self):
        state = _make_state()
        result = map_rooms(state, cache_dir=Path("/nonexistent/cache"))
        assert "error" in result
        assert result["room_map"] == {}

    def test_error_if_no_bid_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = _make_cache(Path(tmp))
            result = map_rooms(_make_state(bid_items=[]), cache_dir=cache_dir)
        assert "error" in result
        assert result["room_map"] == {}

    def test_error_if_bad_spec_url(self):
        state = _make_state(spec_url="https://specbooks.com/bad/url")
        result = map_rooms(state)
        assert "error" in result
        assert result["room_map"] == {}
