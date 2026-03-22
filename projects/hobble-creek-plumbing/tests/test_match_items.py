"""Tests for match_items node."""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "nodes"))

from nodes.match_items import (
    match_items,
    _build_room_match,
    _retry_call,
    BILLING_RULES,
    CONFIDENCE_THRESHOLD,
    SPEC_ONLY_NOTE,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_BID_ITEMS = [
    {"room": "Master Bedroom", "name": "Lav", "bid_qty": 1, "unit_price": None},
    {"room": "Master Bedroom", "name": "Shower", "bid_qty": 1, "unit_price": None},
    {"room": "Master Bedroom", "name": "Toilet", "bid_qty": 1, "unit_price": None},
    {"room": "Main floor", "name": "Sink (Kitchen)", "bid_qty": 1, "unit_price": None},
    {"room": "Main floor", "name": "Water Heater", "bid_qty": 1, "unit_price": None},
]

SAMPLE_SPEC_ITEMS = [
    {"room": "Master Bedroom", "name": "Phylrich Hex Widespread Faucet", "model": "500-12-10B", "qty": 1, "image_url": "spec_images/faucet.jpg"},
    {"room": "Master Bedroom", "name": "Wall Lavatory Valve", "model": "8090536RNL", "qty": 1, "image_url": "spec_images/valve.jpg"},
    {"room": "Master Bedroom", "name": "Brizo Litze Raincan Showerhead", "model": "87435-GL", "qty": 1, "image_url": "spec_images/shower.jpg"},
    {"room": "Master Bedroom", "name": "Toto Nexus Toilet", "model": "MS442124CEFG", "qty": 1, "image_url": "spec_images/toilet.jpg"},
    {"room": "Master Bedroom", "name": "Thermostatic Valve", "model": "T60P085", "qty": 1, "image_url": "spec_images/valve2.jpg"},
    {"room": "Main floor", "name": "Brizo Odin Kitchen Faucet", "model": "63375LF-GLLHP", "qty": 1, "image_url": "spec_images/kitchen.jpg"},
    {"room": "Main floor", "name": "Prep Faucet", "model": "9032LF", "qty": 1, "image_url": "spec_images/prep.jpg"},
]

GEMINI_MASTER_BED_RESPONSE = [
    {"bid_name": "Lav", "primary_spec_index": 0, "sub_spec_indices": [1], "confidence": 0.95, "notes": "Faucet per Lav rule"},
    {"bid_name": "Shower", "primary_spec_index": 2, "sub_spec_indices": [4], "confidence": 0.9, "notes": "Raincan showerhead per Shower rule"},
    {"bid_name": "Toilet", "primary_spec_index": 3, "sub_spec_indices": [], "confidence": 0.98, "notes": "Toilet matched directly"},
]

GEMINI_MAIN_FLOOR_RESPONSE = [
    {"bid_name": "Sink (Kitchen)", "primary_spec_index": 0, "sub_spec_indices": [1], "confidence": 0.92, "notes": "Kitchen faucet per rule"},
    {"bid_name": "Water Heater", "primary_spec_index": None, "sub_spec_indices": [], "confidence": 1.0, "notes": "No spec match — bid-only"},
]


def _make_state(**overrides) -> dict:
    base = {
        "spec_url": "https://specbooks.com/v4/especbook/3408205?token=abc",
        "bid_path": "", "plans_path": "", "cabinets_path": "",
        "job_name": "Test", "output_dir": "",
        "bid_items": SAMPLE_BID_ITEMS,
        "spec_items": SAMPLE_SPEC_ITEMS,
        "rooms": {}, "cabinet_map": {}, "room_map": {},
        "matched_items": [], "review_queue": [], "discrepancies": [],
        "output_data": {}, "logs": [], "error": "",
    }
    base.update(overrides)
    return base


def _mock_llm(*responses):
    """Returns a mock LLM whose .invoke() cycles through responses as JSON strings."""
    mock = MagicMock()
    mock.invoke.side_effect = [
        MagicMock(content=json.dumps(r)) for r in responses
    ]
    return mock


# ── Unit tests: BILLING_RULES ─────────────────────────────────────────────────

class TestBillingRules:
    def test_contains_lav_rule(self):
        assert "Lav" in BILLING_RULES
        assert "faucet" in BILLING_RULES.lower()

    def test_contains_shower_rule(self):
        assert "Shower" in BILLING_RULES
        assert "showerhead" in BILLING_RULES.lower()

    def test_contains_sink_kitchen_rule(self):
        assert "Sink (Kitchen)" in BILLING_RULES
        assert "kitchen faucet" in BILLING_RULES.lower()

    def test_contains_tub_shower_rule(self):
        assert "Tub/Shower" in BILLING_RULES

    def test_contains_steam_shower_rule(self):
        assert "Steam Shower" in BILLING_RULES
        assert "steam generator" in BILLING_RULES.lower()


# ── Unit tests: _retry_call ───────────────────────────────────────────────────

class TestRetryCall:
    def test_succeeds_on_first_try(self):
        fn = MagicMock(return_value="ok")
        assert _retry_call(fn) == "ok"
        assert fn.call_count == 1

    def test_retries_on_503(self):
        fn = MagicMock(side_effect=[Exception("503 service unavailable"), "ok"])
        with patch("nodes.match_items.time.sleep"):
            result = _retry_call(fn, max_retries=2)
        assert result == "ok"
        assert fn.call_count == 2

    def test_raises_after_max_retries(self):
        fn = MagicMock(side_effect=Exception("503 overloaded"))
        with patch("nodes.match_items.time.sleep"):
            with pytest.raises(Exception, match="503"):
                _retry_call(fn, max_retries=3)
        assert fn.call_count == 3

    def test_does_not_retry_on_non_rate_limit(self):
        fn = MagicMock(side_effect=ValueError("invalid input"))
        with pytest.raises(ValueError):
            _retry_call(fn, max_retries=3)
        assert fn.call_count == 1


# ── Unit tests: _build_room_match ─────────────────────────────────────────────

class TestBuildRoomMatch:
    def _run(self, room_bid, room_spec, confirmed=None, gemini_response=None):
        llm = _mock_llm(gemini_response or [])
        return _build_room_match("Test Room", room_bid, room_spec, confirmed or {}, llm)

    def test_matched_items_schema(self):
        room_spec = SAMPLE_SPEC_ITEMS[:5]  # Master Bedroom items
        room_bid = [b for b in SAMPLE_BID_ITEMS if b["room"] == "Master Bedroom"]
        matched, _ = _build_room_match("Master Bedroom", room_bid, room_spec, {}, _mock_llm(GEMINI_MASTER_BED_RESPONSE))
        bid_matches = [m for m in matched if m["notes"] != "spec_only"]
        for item in bid_matches:
            assert "room" in item
            assert "bid_name" in item
            assert "bid_qty" in item
            assert "spec_items" in item
            assert "confidence" in item
            assert "notes" in item

    def test_primary_spec_item_has_is_primary_true(self):
        room_spec = SAMPLE_SPEC_ITEMS[:5]
        room_bid = [b for b in SAMPLE_BID_ITEMS if b["room"] == "Master Bedroom"]
        matched, _ = _build_room_match("Master Bedroom", room_bid, room_spec, {}, _mock_llm(GEMINI_MASTER_BED_RESPONSE))
        lav_match = next(m for m in matched if m["bid_name"] == "Lav")
        assert lav_match["spec_items"][0]["is_primary"] is True

    def test_sub_items_have_is_primary_false(self):
        room_spec = SAMPLE_SPEC_ITEMS[:5]
        room_bid = [b for b in SAMPLE_BID_ITEMS if b["room"] == "Master Bedroom"]
        matched, _ = _build_room_match("Master Bedroom", room_bid, room_spec, {}, _mock_llm(GEMINI_MASTER_BED_RESPONSE))
        lav_match = next(m for m in matched if m["bid_name"] == "Lav")
        sub_items = [s for s in lav_match["spec_items"] if not s["is_primary"]]
        assert len(sub_items) == 1
        assert sub_items[0]["is_primary"] is False

    def test_bid_item_no_spec_match_gets_empty_spec_items(self):
        room_spec = SAMPLE_SPEC_ITEMS[5:]  # Main floor specs
        room_bid = [b for b in SAMPLE_BID_ITEMS if b["room"] == "Main floor"]
        matched, _ = _build_room_match("Main floor", room_bid, room_spec, {}, _mock_llm(GEMINI_MAIN_FLOOR_RESPONSE))
        water_heater = next((m for m in matched if m["bid_name"] == "Water Heater"), None)
        assert water_heater is not None
        assert water_heater["spec_items"] == []

    def test_review_queue_for_low_confidence(self):
        low_conf_response = [
            {"bid_name": "Lav", "primary_spec_index": 0, "sub_spec_indices": [], "confidence": 0.7, "notes": "uncertain"},
        ]
        room_spec = SAMPLE_SPEC_ITEMS[:1]
        room_bid = [{"room": "Test Room", "name": "Lav", "bid_qty": 1, "unit_price": None}]
        matched, review = _build_room_match("Test Room", room_bid, room_spec, {}, _mock_llm(low_conf_response))
        assert len(review) == 1
        assert review[0]["bid_name"] == "Lav"
        assert review[0]["confidence"] == 0.7

    def test_high_confidence_not_in_review(self):
        room_spec = SAMPLE_SPEC_ITEMS[:5]
        room_bid = [b for b in SAMPLE_BID_ITEMS if b["room"] == "Master Bedroom"]
        matched, review = _build_room_match("Master Bedroom", room_bid, room_spec, {}, _mock_llm(GEMINI_MASTER_BED_RESPONSE))
        assert len(review) == 0

    def test_spec_only_added_for_unmatched_spec_item(self):
        # Gemini matches Lav (index 0) only — spec item at index 1 should be spec_only
        partial_response = [
            {"bid_name": "Lav", "primary_spec_index": 0, "sub_spec_indices": [], "confidence": 0.95, "notes": "matched"},
        ]
        room_spec = SAMPLE_SPEC_ITEMS[:2]
        room_bid = [{"room": "Test Room", "name": "Lav", "bid_qty": 1, "unit_price": None}]
        matched, _ = _build_room_match("Test Room", room_bid, room_spec, {}, _mock_llm(partial_response))
        spec_only = [m for m in matched if m["notes"] == SPEC_ONLY_NOTE]
        assert len(spec_only) == 1
        assert spec_only[0]["bid_qty"] == 0

    def test_confirmed_match_skips_gemini(self):
        confirmed = {
            "Master Bedroom:Lav": {
                "primary_model": "500-12-10B",
                "sub_models": [],
                "confidence": 1.0,
                "notes": "human confirmed",
            }
        }
        llm = MagicMock()
        room_bid = [{"room": "Master Bedroom", "name": "Lav", "bid_qty": 1, "unit_price": None}]
        room_spec = SAMPLE_SPEC_ITEMS[:2]
        _build_room_match("Master Bedroom", room_bid, room_spec, confirmed, llm)
        llm.invoke.assert_not_called()

    def test_confirmed_match_uses_stored_model(self):
        confirmed = {
            "Master Bedroom:Lav": {
                "primary_model": "500-12-10B",
                "sub_models": ["8090536RNL"],
                "confidence": 1.0,
                "notes": "confirmed",
            }
        }
        llm = MagicMock()
        room_bid = [{"room": "Master Bedroom", "name": "Lav", "bid_qty": 1, "unit_price": None}]
        room_spec = SAMPLE_SPEC_ITEMS[:2]
        matched, _ = _build_room_match("Master Bedroom", room_bid, room_spec, confirmed, llm)
        lav = next(m for m in matched if m["bid_name"] == "Lav")
        assert lav["spec_items"][0]["model"] == "500-12-10B"


# ── Integration: match_items node ────────────────────────────────────────────

class TestMatchItemsNode:
    def _run(self, state, *llm_responses):
        mock_llm = _mock_llm(*llm_responses)
        with patch("nodes.match_items.ChatGoogleGenerativeAI", return_value=mock_llm):
            with patch("nodes.match_items._load_confirmed", return_value={}):
                return match_items(state)

    def test_returns_matched_items_key(self):
        result = self._run(_make_state(), GEMINI_MASTER_BED_RESPONSE, GEMINI_MAIN_FLOOR_RESPONSE)
        assert "matched_items" in result

    def test_returns_review_queue_key(self):
        result = self._run(_make_state(), GEMINI_MASTER_BED_RESPONSE, GEMINI_MAIN_FLOOR_RESPONSE)
        assert "review_queue" in result

    def test_logs_populated(self):
        result = self._run(_make_state(), GEMINI_MASTER_BED_RESPONSE, GEMINI_MAIN_FLOOR_RESPONSE)
        assert result.get("logs")
        assert any("match_items" in log for log in result["logs"])

    def test_error_if_no_bid_items(self):
        result = self._run(_make_state(bid_items=[]))
        assert "error" in result
        assert result["matched_items"] == []

    def test_gemini_called_once_per_room(self):
        mock_llm = _mock_llm(GEMINI_MASTER_BED_RESPONSE, GEMINI_MAIN_FLOOR_RESPONSE)
        with patch("nodes.match_items.ChatGoogleGenerativeAI", return_value=mock_llm):
            with patch("nodes.match_items._load_confirmed", return_value={}):
                match_items(_make_state())
        assert mock_llm.invoke.call_count == 2  # 2 rooms
