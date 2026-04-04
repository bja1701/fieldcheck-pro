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
    _is_plan_sourced,
    _fix_unmatched_urinals,
    BILLING_RULES,
    CONFIDENCE_THRESHOLD,
    SPEC_ONLY_NOTE,
    PLAN_SOURCED_NOTE,
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

    def test_room_map_translates_raw_spec_room_names(self):
        """Spec items with raw spec room names are translated via room_map before matching."""
        spec_items_raw = [
            {"room": "OWNERS SUITE", "name": "Brizo Faucet", "model": "ABC-1", "qty": 1, "image_url": ""},
        ]
        bid_items = [
            {"room": "Master Bedroom", "name": "Lav", "bid_qty": 1, "unit_price": None},
        ]
        room_map = {"OWNERS SUITE": "Master Bedroom"}
        gemini_response = [
            {"bid_name": "Lav", "primary_spec_index": 0, "sub_spec_indices": [], "confidence": 0.95, "notes": "matched"}
        ]
        state = _make_state(bid_items=bid_items, spec_items=spec_items_raw, room_map=room_map)
        result = self._run(state, gemini_response)
        matched = [m for m in result["matched_items"] if m["notes"] != "spec_only"]
        assert len(matched) == 1
        assert matched[0]["room"] == "Master Bedroom"

    def test_room_map_null_value_discards_spec_items(self):
        """Spec items whose room maps to None in room_map are discarded (fixture by others)."""
        spec_items_raw = [
            {"room": "TERRACE LEVEL FULL BATH (FAUCETS BY OTHERS)", "name": "Some Faucet", "model": "X", "qty": 1, "image_url": ""},
        ]
        bid_items = [
            {"room": "Master Bedroom", "name": "Lav", "bid_qty": 1, "unit_price": None},
        ]
        room_map = {"TERRACE LEVEL FULL BATH (FAUCETS BY OTHERS)": None}
        gemini_response = [
            {"bid_name": "Lav", "primary_spec_index": None, "sub_spec_indices": [], "confidence": 1.0, "notes": "no spec match"}
        ]
        state = _make_state(bid_items=bid_items, spec_items=spec_items_raw, room_map=room_map)
        result = self._run(state, gemini_response)
        spec_items_in_output = [i for m in result["matched_items"] for i in m.get("spec_items", [])]
        assert all("FAUCETS BY OTHERS" not in i.get("name", "") for i in spec_items_in_output)


# ── Unit tests: _is_plan_sourced ─────────────────────────────────────────────

class TestIsPlanSourced:
    def test_hose_bib_is_plan_sourced(self):
        assert _is_plan_sourced("Hose Bib") is True

    def test_hot_cold_hose_bib_is_plan_sourced(self):
        assert _is_plan_sourced("Hot/Cold Hose Bib") is True

    def test_washer_box_is_plan_sourced(self):
        assert _is_plan_sourced("Washer Box") is True

    def test_ice_bin_is_plan_sourced(self):
        assert _is_plan_sourced("Ice bin hook up") is True

    def test_refrigerator_water_line_is_plan_sourced(self):
        assert _is_plan_sourced("Refrigerator Water-Line") is True

    def test_refridgerator_typo_is_plan_sourced(self):
        assert _is_plan_sourced("Refridgerator Water-Line") is True

    def test_dog_wash_is_plan_sourced(self):
        assert _is_plan_sourced("Dog Wash") is True

    def test_toilet_is_not_plan_sourced(self):
        assert _is_plan_sourced("Toilet") is False

    def test_lav_is_not_plan_sourced(self):
        assert _is_plan_sourced("Lav") is False

    def test_shower_is_not_plan_sourced(self):
        assert _is_plan_sourced("Shower") is False

    def test_urinal_is_not_plan_sourced(self):
        assert _is_plan_sourced("Urinal") is False

    def test_case_insensitive(self):
        assert _is_plan_sourced("hose bib") is True
        assert _is_plan_sourced("WASHER BOX") is True


# ── Unit tests: plan-sourced in _build_room_match ────────────────────────────

class TestPlanSourcedInRoomMatch:
    def test_plan_sourced_item_gets_plan_sourced_note(self):
        room_bid = [{"room": "Main floor", "name": "Hose Bib", "bid_qty": 2, "unit_price": None}]
        room_spec = [{"room": "Main floor", "name": "Some Faucet", "model": "X", "qty": 1, "image_url": ""}]
        llm = MagicMock()
        matched, _ = _build_room_match("Main floor", room_bid, room_spec, {}, llm)
        hose_bib = next(m for m in matched if m["bid_name"] == "Hose Bib")
        assert hose_bib["notes"] == PLAN_SOURCED_NOTE

    def test_plan_sourced_item_has_empty_spec_items(self):
        room_bid = [{"room": "Main floor", "name": "Hose Bib", "bid_qty": 1, "unit_price": None}]
        room_spec = []
        llm = MagicMock()
        matched, _ = _build_room_match("Main floor", room_bid, room_spec, {}, llm)
        hose_bib = next(m for m in matched if m["bid_name"] == "Hose Bib")
        assert hose_bib["spec_items"] == []

    def test_plan_sourced_item_skips_gemini(self):
        """LLM should NOT be called for plan-sourced items."""
        room_bid = [{"room": "Main floor", "name": "Hose Bib", "bid_qty": 1, "unit_price": None}]
        room_spec = [{"room": "Main floor", "name": "Some Spec", "model": "X", "qty": 1, "image_url": ""}]
        llm = MagicMock()
        _build_room_match("Main floor", room_bid, room_spec, {}, llm)
        llm.invoke.assert_not_called()

    def test_plan_sourced_item_not_in_review_queue(self):
        room_bid = [{"room": "Main floor", "name": "Washer Box", "bid_qty": 1, "unit_price": None}]
        room_spec = []
        llm = MagicMock()
        _, review = _build_room_match("Main floor", room_bid, room_spec, {}, llm)
        assert len(review) == 0

    def test_plan_sourced_preserves_bid_qty(self):
        room_bid = [{"room": "Main floor", "name": "Hose Bib", "bid_qty": 3, "unit_price": None}]
        llm = MagicMock()
        matched, _ = _build_room_match("Main floor", room_bid, [], {}, llm)
        assert matched[0]["bid_qty"] == 3

    def test_non_plan_sourced_still_uses_gemini(self):
        """Non-plan-sourced items still go through Gemini."""
        room_bid = [{"room": "Master Bedroom", "name": "Toilet", "bid_qty": 1, "unit_price": None}]
        room_spec = [{"room": "Master Bedroom", "name": "Toto Nexus", "model": "MS44", "qty": 1, "image_url": ""}]
        gemini_resp = [{"bid_name": "Toilet", "primary_spec_index": 0, "sub_spec_indices": [], "confidence": 0.98, "notes": "matched"}]
        llm = _mock_llm(gemini_resp)
        _build_room_match("Master Bedroom", room_bid, room_spec, {}, llm)
        assert llm.invoke.call_count == 1


# ── Unit tests: _fix_unmatched_urinals ───────────────────────────────────────

class TestFixUnmatchedUrinals:
    _URINAL_SPEC = {"room": "Half Bath", "name": "Toto Urinal", "model": "UT104E", "qty": 1, "image_url": "spec_images/urinal.jpg"}

    def test_unmatched_urinal_gets_cross_room_spec(self):
        matched = [{
            "room": "1/2 Bath 1", "bid_name": "Urinal", "bid_qty": 1,
            "unit_price": None, "spec_items": [], "confidence": 1.0, "notes": "no spec items in room",
        }]
        result = _fix_unmatched_urinals(matched, [self._URINAL_SPEC])
        urinal = next(m for m in result if m["bid_name"] == "Urinal")
        assert len(urinal["spec_items"]) == 1
        assert urinal["spec_items"][0]["is_primary"] is True

    def test_unmatched_urinal_spec_item_has_urinal_in_name(self):
        matched = [{
            "room": "1/2 Bath 1", "bid_name": "Urinal", "bid_qty": 1,
            "unit_price": None, "spec_items": [], "confidence": 1.0, "notes": "no spec items in room",
        }]
        result = _fix_unmatched_urinals(matched, [self._URINAL_SPEC])
        spec = result[0]["spec_items"][0]
        assert "urinal" in spec["name"].lower()

    def test_fallback_sets_confidence_0_9(self):
        matched = [{
            "room": "1/2 Bath 1", "bid_name": "Urinal", "bid_qty": 1,
            "unit_price": None, "spec_items": [], "confidence": 1.0, "notes": "no spec items in room",
        }]
        result = _fix_unmatched_urinals(matched, [self._URINAL_SPEC])
        assert result[0]["confidence"] == 0.9

    def test_already_matched_urinal_not_overwritten(self):
        existing_spec = {"name": "Existing Urinal Match", "model": "X1", "qty": 1, "image_url": "", "is_primary": True}
        matched = [{
            "room": "1/2 Bath 1", "bid_name": "Urinal", "bid_qty": 1,
            "unit_price": None, "spec_items": [existing_spec], "confidence": 0.95, "notes": "matched",
        }]
        result = _fix_unmatched_urinals(matched, [self._URINAL_SPEC])
        # Should not overwrite existing match
        assert result[0]["spec_items"][0]["name"] == "Existing Urinal Match"

    def test_no_urinal_specs_returns_unchanged(self):
        matched = [{
            "room": "1/2 Bath 1", "bid_name": "Urinal", "bid_qty": 1,
            "unit_price": None, "spec_items": [], "confidence": 1.0, "notes": "no spec items in room",
        }]
        non_urinal_spec = {"name": "Kitchen Faucet", "model": "K1", "qty": 1, "image_url": ""}
        result = _fix_unmatched_urinals(matched, [non_urinal_spec])
        assert result[0]["spec_items"] == []

    def test_plan_sourced_urinal_not_overwritten(self):
        """Plan-sourced urinals (if they exist) should not be touched by fallback."""
        matched = [{
            "room": "1/2 Bath 1", "bid_name": "Urinal", "bid_qty": 1,
            "unit_price": None, "spec_items": [], "confidence": 1.0, "notes": PLAN_SOURCED_NOTE,
        }]
        result = _fix_unmatched_urinals(matched, [self._URINAL_SPEC])
        assert result[0]["spec_items"] == []

    def test_non_urinal_bid_items_untouched(self):
        matched = [
            {"room": "Main floor", "bid_name": "Lav", "bid_qty": 1, "unit_price": None, "spec_items": [], "confidence": 1.0, "notes": "no spec items in room"},
            {"room": "1/2 Bath 1", "bid_name": "Urinal", "bid_qty": 1, "unit_price": None, "spec_items": [], "confidence": 1.0, "notes": "no spec items in room"},
        ]
        result = _fix_unmatched_urinals(matched, [self._URINAL_SPEC])
        lav = next(m for m in result if m["bid_name"] == "Lav")
        assert lav["spec_items"] == []


# ── Integration: plan_sourced in match_items node ────────────────────────────

class TestMatchItemsNodePlanSourced:
    def _run(self, state, *llm_responses):
        mock_llm = _mock_llm(*llm_responses)
        with patch("nodes.match_items.ChatGoogleGenerativeAI", return_value=mock_llm):
            with patch("nodes.match_items._load_confirmed", return_value={}):
                return match_items(state)

    def test_plan_sourced_items_in_output(self):
        """Hose Bib in bid should appear in matched_items as plan_sourced."""
        bid_items = [
            {"room": "Main floor", "name": "Hose Bib", "bid_qty": 2, "unit_price": None},
            {"room": "Main floor", "name": "Sink (Kitchen)", "bid_qty": 1, "unit_price": None},
        ]
        spec_items = [
            {"room": "Main floor", "name": "Brizo Kitchen Faucet", "model": "ABC", "qty": 1, "image_url": ""},
        ]
        gemini_resp = [
            {"bid_name": "Sink (Kitchen)", "primary_spec_index": 0, "sub_spec_indices": [], "confidence": 0.95, "notes": "matched"},
        ]
        state = _make_state(bid_items=bid_items, spec_items=spec_items)
        result = self._run(state, gemini_resp)
        hose_bib = next((m for m in result["matched_items"] if m["bid_name"] == "Hose Bib"), None)
        assert hose_bib is not None
        assert hose_bib["notes"] == PLAN_SOURCED_NOTE
        assert hose_bib["spec_items"] == []

    def test_urinal_cross_room_fallback_in_full_node(self):
        """Unmatched Urinal bid item gets cross-room fallback applied by match_items node."""
        bid_items = [
            {"room": "1/2 Bath 1", "name": "Urinal", "bid_qty": 1, "unit_price": None},
        ]
        # Spec book has urinal in a different room (unmapped)
        spec_items = [
            {"room": "Different Room", "name": "Toto Urinal", "model": "UT104E", "qty": 1, "image_url": ""},
        ]
        # Gemini returns no match (no spec items in bid room)
        gemini_resp = [
            {"bid_name": "Urinal", "primary_spec_index": None, "sub_spec_indices": [], "confidence": 1.0, "notes": "no spec items in room"},
        ]
        state = _make_state(bid_items=bid_items, spec_items=spec_items)
        result = self._run(state, gemini_resp)
        urinal = next((m for m in result["matched_items"] if m["bid_name"] == "Urinal"), None)
        assert urinal is not None
        assert len(urinal["spec_items"]) == 1
        assert "urinal" in urinal["spec_items"][0]["name"].lower()


# ── BILLING_RULES content checks ─────────────────────────────────────────────

class TestBillingRulesSubItemRules:
    def test_shower_arm_is_sub_item(self):
        assert "shower arm" in BILLING_RULES.lower()

    def test_tub_spout_is_sub_item(self):
        assert "tub spout" in BILLING_RULES.lower()

    def test_hand_shower_outlet_is_sub_item(self):
        assert "hand shower" in BILLING_RULES.lower()

    def test_rough_in_valve_is_sub_item(self):
        assert "rough-in valve" in BILLING_RULES.lower()

    def test_urinal_rule_present(self):
        assert "Urinal" in BILLING_RULES
        assert "urinal" in BILLING_RULES.lower()
