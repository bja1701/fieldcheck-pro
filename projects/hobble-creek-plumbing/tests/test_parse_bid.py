"""Tests for parse_bid node."""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "nodes"))

from nodes.parse_bid import parse_bid

FIXTURES = Path(__file__).parent.parent / "fixtures"
BAKER_CSV = FIXTURES / "baker_bid.csv"


def _make_state(bid_path: str) -> dict:
    return {
        "spec_url": "", "bid_path": bid_path, "plans_path": "", "cabinets_path": "",
        "job_name": "Test", "bid_items": [], "spec_items": [], "rooms": {},
        "cabinet_map": {}, "matched_items": [], "review_queue": [], "discrepancies": [],
        "output_data": {}, "logs": [], "error": "",
    }


class TestParseBidCsv:
    def test_extracts_items(self):
        result = parse_bid(_make_state(str(BAKER_CSV)))
        items = result["bid_items"]
        assert len(items) >= 40, f"Expected 40+ items, got {len(items)}"

    def test_item_schema(self):
        items = parse_bid(_make_state(str(BAKER_CSV)))["bid_items"]
        for item in items:
            assert "room" in item
            assert "name" in item
            assert "bid_qty" in item
            assert "unit_price" in item

    def test_rooms_are_populated(self):
        items = parse_bid(_make_state(str(BAKER_CSV)))["bid_items"]
        rooms = {i["room"] for i in items}
        assert "Basement" in rooms
        assert "Master Bedroom" in rooms

    def test_quantities_are_int(self):
        items = parse_bid(_make_state(str(BAKER_CSV)))["bid_items"]
        for item in items:
            assert isinstance(item["bid_qty"], int), f"bid_qty not int for {item['name']}"

    def test_skips_no_skip_rows(self):
        # baker_bid.csv has no summary rows but ensure nothing is accidentally skipped
        items = parse_bid(_make_state(str(BAKER_CSV)))["bid_items"]
        names = [i["name"] for i in items]
        assert "Water Heater" in names
        assert "Toilet" in names
        assert "Shower (2nd Head)" in names

    def test_water_heater_present(self):
        """Water heater has no spec equivalent — must still appear."""
        items = parse_bid(_make_state(str(BAKER_CSV)))["bid_items"]
        heaters = [i for i in items if "Water Heater" in i["name"]]
        assert heaters, "Water Heater should be in bid items"

    def test_prices_parsed(self):
        items = parse_bid(_make_state(str(BAKER_CSV)))["bid_items"]
        priced = [i for i in items if i["unit_price"] is not None]
        assert priced, "At least some items should have prices"

    def test_logs_populated(self):
        result = parse_bid(_make_state(str(BAKER_CSV)))
        assert result["logs"]
        assert "parse_bid" in result["logs"][0]
