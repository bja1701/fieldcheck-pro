"""Tests for generate_output node."""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "nodes"))

from nodes.generate_output import (
    generate_output,
    _compute_status,
    _build_item,
    _floor_for_room,
    _cabinet_pages_for_room,
    _bid_rooms_ordered,
    BILLABLE_ITEMS,
    HIDE_ITEMS,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_BID_ITEMS = [
    {"room": "Main floor", "name": "Sink (Kitchen)", "bid_qty": 2, "unit_price": None},
    {"room": "Main floor", "name": "Water Heater", "bid_qty": 1, "unit_price": None},
    {"room": "Master Bedroom", "name": "Lav", "bid_qty": 2, "unit_price": None},
    {"room": "Master Bedroom", "name": "Toilet", "bid_qty": 1, "unit_price": None},
    {"room": "Basement", "name": "Floor Drain", "bid_qty": 3, "unit_price": None},
]

_KITCHEN_FAUCET = {
    "name": "Brizo - Odin Kitchen Faucet",
    "model": "63375LF-GLLHP",
    "qty": 1,
    "image_url": "spec_images/Brizo - Odin Kitchen Faucet - 63375LF-GLLHP.jpg",
    "is_primary": True,
}
_FAUCET_VALVE = {
    "name": "Shutoff Valve",
    "model": "V-001",
    "qty": 1,
    "image_url": "spec_images/Shutoff Valve - V-001.jpg",
    "is_primary": False,
}
_LAV_FAUCET = {
    "name": "Brizo - Allaria Widespread Faucet",
    "model": "65367LF-GLLHP",
    "qty": 2,
    "image_url": "spec_images/Brizo - Allaria Widespread Faucet - 65367LF-GLLHP.jpg",
    "is_primary": True,
}

SAMPLE_MATCHED_ITEMS = [
    {
        "room": "Main floor", "bid_name": "Sink (Kitchen)", "bid_qty": 2,
        "unit_price": None, "spec_items": [_KITCHEN_FAUCET], "confidence": 0.95, "notes": "",
    },
    {
        "room": "Main floor", "bid_name": "Water Heater", "bid_qty": 1,
        "unit_price": None, "spec_items": [], "confidence": 1.0, "notes": "no spec match",
    },
    {
        "room": "Master Bedroom", "bid_name": "Lav", "bid_qty": 2,
        "unit_price": None, "spec_items": [_LAV_FAUCET, _FAUCET_VALVE], "confidence": 0.95, "notes": "",
    },
    {
        "room": "Master Bedroom", "bid_name": "Toilet", "bid_qty": 1,
        "unit_price": None,
        "spec_items": [{"name": "Toto Nexus Toilet", "model": "MS442124CEFG", "qty": 1, "image_url": "spec_images/toto.jpg", "is_primary": True}],
        "confidence": 0.98, "notes": "",
    },
    {
        "room": "Basement", "bid_name": "Floor Drain", "bid_qty": 3,
        "unit_price": None, "spec_items": [], "confidence": 1.0, "notes": "no spec match",
    },
    # spec_only item
    {
        "room": "Master Bedroom", "bid_name": "Urinal", "bid_qty": 0,
        "unit_price": None,
        "spec_items": [{"name": "Toto Urinal", "model": "UT104E", "qty": 1, "image_url": "spec_images/urinal.jpg", "is_primary": True}],
        "confidence": 1.0, "notes": "spec_only",
    },
]

SAMPLE_ROOMS_STATE = {
    "rooms": {
        "main": ["kitchen", "main floor", "mud room"],
        "basement": ["basement", "golf simulator"],
        "upper": ["upper floor", "bathroom 3"],
    },
    "planNavigation": {
        "main": {"pages": [6, 7], "images": ["plan_images/plan-06.jpg", "plan_images/plan-07.jpg"]},
        "basement": {"pages": [4, 5], "images": ["plan_images/plan-04.jpg", "plan_images/plan-05.jpg"]},
        "upper": {"pages": [8, 9], "images": ["plan_images/plan-08.jpg", "plan_images/plan-09.jpg"]},
    },
}

SAMPLE_CABINET_MAP = {
    "KITCHEN": [1, 2, 3],
    "MASTER BATH": [18],
    "BATH 2": [19],
}

SAMPLE_ROOM_MAP = {
    "KITCHEN": "Main floor",
    "MASTER BATH": "Master Bedroom",
    "BATH 2": "Bathroom 2",
}


def _make_state(**overrides) -> dict:
    base = {
        "spec_url": "https://specbooks.com/v4/especbook/123?token=abc",
        "bid_path": "", "plans_path": "", "cabinets_path": "",
        "job_name": "Baker Residence", "output_dir": "",
        "bid_items": SAMPLE_BID_ITEMS,
        "spec_items": [], "rooms": SAMPLE_ROOMS_STATE,
        "cabinet_map": SAMPLE_CABINET_MAP, "room_map": SAMPLE_ROOM_MAP,
        "matched_items": SAMPLE_MATCHED_ITEMS, "review_queue": [],
        "discrepancies": [], "output_data": {}, "logs": [], "error": "",
    }
    base.update(overrides)
    return base


# ── Unit: _compute_status ─────────────────────────────────────────────────────

class TestComputeStatus:
    def test_ok_when_spec_qty_zero(self):
        assert _compute_status(1, 0) == "ok"

    def test_ok_when_bid_qty_greater_and_spec_zero(self):
        assert _compute_status(3, 0) == "ok"

    def test_pending_when_bid_qty_zero(self):
        assert _compute_status(0, 1) == "pending"

    def test_match_when_equal(self):
        assert _compute_status(2, 2) == "match"

    def test_extra_in_bid_when_bid_greater(self):
        assert _compute_status(3, 1) == "extra_in_bid"

    def test_missing_from_bid_when_spec_greater(self):
        assert _compute_status(1, 3) == "missing_from_bid"


# ── Unit: _build_item ─────────────────────────────────────────────────────────

class TestBuildItem:
    def test_schema_keys_present(self):
        item = _build_item(SAMPLE_MATCHED_ITEMS[0])
        assert "name" in item
        assert "bidQty" in item
        assert "specQty" in item
        assert "specImage" in item
        assert "specDesc" in item
        assert "status" in item

    def test_spec_qty_from_primary_qty(self):
        item = _build_item(SAMPLE_MATCHED_ITEMS[0])  # Kitchen faucet qty=1
        assert item["specQty"] == 1

    def test_spec_desc_from_primary_name(self):
        item = _build_item(SAMPLE_MATCHED_ITEMS[0])
        assert item["specDesc"] == "Brizo - Odin Kitchen Faucet"

    def test_spec_image_from_primary_image_url(self):
        item = _build_item(SAMPLE_MATCHED_ITEMS[0])
        assert "Brizo - Odin Kitchen Faucet" in item["specImage"]

    def test_no_spec_gets_null_image(self):
        item = _build_item(SAMPLE_MATCHED_ITEMS[1])  # Water Heater, no spec
        assert item["specImage"] is None
        assert item["specQty"] == 0
        assert item["status"] == "ok"

    def test_sub_items_present_when_subs_exist(self):
        item = _build_item(SAMPLE_MATCHED_ITEMS[2])  # Lav with sub-item
        assert "subItems" in item
        assert len(item["subItems"]) == 1

    def test_sub_items_schema(self):
        item = _build_item(SAMPLE_MATCHED_ITEMS[2])
        sub = item["subItems"][0]
        assert "name" in sub
        assert "model" in sub
        assert "img" in sub

    def test_no_sub_items_key_when_no_subs(self):
        item = _build_item(SAMPLE_MATCHED_ITEMS[3])  # Toilet, no subs
        assert "subItems" not in item

    def test_spec_only_gets_pending_status(self):
        item = _build_item(SAMPLE_MATCHED_ITEMS[5])  # bid_qty=0
        assert item["status"] == "pending"

    def test_extra_in_bid_status(self):
        # bid_qty=2, spec_qty=1 → extra_in_bid
        matched = {**SAMPLE_MATCHED_ITEMS[0], "bid_qty": 2}  # Kitchen faucet specQty=1
        item = _build_item(matched)
        assert item["status"] == "extra_in_bid"

    def test_missing_from_bid_status(self):
        # bid_qty=1, spec_qty=3 → missing_from_bid
        primary = {**_KITCHEN_FAUCET, "qty": 3}
        matched = {"bid_name": "Shower", "bid_qty": 1, "spec_items": [primary]}
        item = _build_item(matched)
        assert item["status"] == "missing_from_bid"


# ── Unit: _floor_for_room ─────────────────────────────────────────────────────

class TestFloorForRoom:
    def test_basement_keyword(self):
        assert _floor_for_room("Basement", {}) == "basement"

    def test_upper_keyword(self):
        assert _floor_for_room("Upper Floor", {}) == "upper"

    def test_main_default(self):
        assert _floor_for_room("Master Bedroom", {}) == "main"

    def test_uses_rooms_state_match(self):
        # "golf simulator" appears in basement rooms list
        result = _floor_for_room("Golf Simulator", SAMPLE_ROOMS_STATE)
        assert result == "basement"


# ── Unit: _cabinet_pages_for_room ─────────────────────────────────────────────

class TestCabinetPagesForRoom:
    def test_maps_via_room_map(self):
        pages = _cabinet_pages_for_room("Main floor", SAMPLE_CABINET_MAP, SAMPLE_ROOM_MAP)
        assert pages == [1, 2, 3]

    def test_returns_empty_when_no_match(self):
        pages = _cabinet_pages_for_room("Nonexistent Room", SAMPLE_CABINET_MAP, SAMPLE_ROOM_MAP)
        assert pages == []

    def test_deduplicates_and_sorts(self):
        cabinet_map = {"ROOM A": [3, 1, 2], "ROOM B": [1, 4]}
        room_map = {"ROOM A": "Test Room", "ROOM B": "Test Room"}
        pages = _cabinet_pages_for_room("Test Room", cabinet_map, room_map)
        assert pages == [1, 2, 3, 4]


# ── Integration: generate_output ─────────────────────────────────────────────

class TestGenerateOutput:
    def test_returns_output_data_key(self):
        result = generate_output(_make_state())
        assert "output_data" in result

    def test_project_name_set(self):
        result = generate_output(_make_state())
        assert result["output_data"]["project"] == "Baker Residence"

    def test_rooms_list_present(self):
        result = generate_output(_make_state())
        assert isinstance(result["output_data"]["rooms"], list)

    def test_room_order_matches_bid_items(self):
        result = generate_output(_make_state())
        names = [r["name"] for r in result["output_data"]["rooms"]]
        assert names.index("Main floor") < names.index("Master Bedroom")

    def test_plan_navigation_present(self):
        result = generate_output(_make_state())
        assert "planNavigation" in result["output_data"]
        assert "main" in result["output_data"]["planNavigation"]

    def test_cabinet_pages_populated(self):
        result = generate_output(_make_state())
        main_room = next(r for r in result["output_data"]["rooms"] if r["name"] == "Main floor")
        assert main_room["cabinetPages"] == [1, 2, 3]

    def test_cabinet_images_formatted(self):
        result = generate_output(_make_state())
        main_room = next(r for r in result["output_data"]["rooms"] if r["name"] == "Main floor")
        assert main_room["cabinetImages"] == [
            "cabinet_images/page-01.png",
            "cabinet_images/page-02.png",
            "cabinet_images/page-03.png",
        ]

    def test_logs_populated(self):
        result = generate_output(_make_state())
        assert result.get("logs")

    def test_error_if_no_matched_items(self):
        result = generate_output(_make_state(matched_items=[]))
        assert "error" in result

    def test_data_js_written_when_output_dir_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = generate_output(_make_state(output_dir=tmp))
            data_js = Path(tmp) / "data.js"
            assert data_js.exists()

    def test_data_js_contains_billable_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            generate_output(_make_state(output_dir=tmp))
            content = (Path(tmp) / "data.js").read_text()
            assert "BILLABLE_ITEMS" in content

    def test_data_js_contains_hide_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            generate_output(_make_state(output_dir=tmp))
            content = (Path(tmp) / "data.js").read_text()
            assert "HIDE_ITEMS" in content

    def test_data_js_contains_job_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            generate_output(_make_state(output_dir=tmp))
            content = (Path(tmp) / "data.js").read_text()
            assert "JOB_DATA" in content
            assert "Baker Residence" in content

    def test_no_data_js_when_output_dir_empty(self):
        result = generate_output(_make_state(output_dir=""))
        assert "output_data" in result
        assert result["output_data"]["project"] == "Baker Residence"
