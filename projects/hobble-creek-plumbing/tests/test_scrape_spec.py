"""Tests for scrape_spec node — mocks all HTTP calls."""
from __future__ import annotations
import sys, json, base64, time
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "nodes"))

from nodes.scrape_spec import scrape_spec, _extract_id_token, _convert, ROOM_MAP


def _make_state(**overrides) -> dict:
    base = {
        "spec_url": "https://specbooks.com/v4/especbook/3408205?token=abc123",
        "bid_path": "", "plans_path": "", "cabinets_path": "",
        "job_name": "Test", "bid_items": [
            {"room": "Master Bedroom", "name": "Toilet", "bid_qty": 1, "unit_price": None},
        ],
        "spec_items": [], "rooms": {}, "cabinet_map": {},
        "matched_items": [], "review_queue": [], "discrepancies": [],
        "output_data": {}, "logs": [], "error": "",
    }
    base.update(overrides)
    return base


def _make_jwt(sub: str = "user42") -> str:
    payload = base64.b64encode(json.dumps({"sub": sub}).encode()).decode().rstrip("=")
    return f"header.{payload}.sig"


def _mock_auth_response(sub="user42"):
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {"access_token": _make_jwt(sub)}
    m.raise_for_status = MagicMock()
    return m


def _mock_categories():
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = [
        {"id": "cat1", "name": "Master Bath"},
        {"id": "cat2", "name": "Toilets"},
    ]
    m.raise_for_status = MagicMock()
    return m


def _mock_specs_master_bath():
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {
        "data": [
            {"manufacturerName": "Brizo", "name": "Litze Raincan Showerhead", "modelNumber": "87435-GL", "qty": 1, "imageName": "brizo-showerhead.jpg"},
        ],
        "meta": {"last_page": 1},
    }
    m.raise_for_status = MagicMock()
    return m


def _mock_specs_toilets():
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {
        "data": [
            {"manufacturerName": "Toto", "name": "Nexus Close Coupled Toilet", "modelNumber": "MS442124CEFG", "qty": 1, "imageName": "toto-toilet.jpg"},
        ],
        "meta": {"last_page": 1},
    }
    m.raise_for_status = MagicMock()
    return m


class TestExtractIdToken:
    def test_extracts_id_and_token(self):
        spec_id, token = _extract_id_token("https://specbooks.com/v4/especbook/3408205?token=640f423e")
        assert spec_id == "3408205"
        assert token == "640f423e"

    def test_raises_without_token(self):
        import pytest
        with pytest.raises(ValueError, match="token"):
            _extract_id_token("https://specbooks.com/v4/especbook/3408205")

    def test_raises_without_id(self):
        import pytest
        with pytest.raises(ValueError, match="specbook ID"):
            _extract_id_token("https://specbooks.com/v4/something?token=abc")


class TestScrapeSpecMocked:
    def _run_with_mocks(self, state: dict) -> dict:
        side_effects = [
            _mock_auth_response(),
            _mock_categories(),
            _mock_specs_master_bath(),
            _mock_specs_toilets(),
        ]
        with patch("nodes.scrape_spec.CACHE_DIR", Path("/tmp/scrape_spec_test_cache")):
            # Remove cache file so it actually calls the API mock
            cache = Path("/tmp/scrape_spec_test_cache") / "raw_3408205.json"
            cache.parent.mkdir(exist_ok=True)
            if cache.exists():
                cache.unlink()
            with patch("requests.post", return_value=side_effects[0]):
                with patch("requests.get", side_effect=side_effects[1:]):
                    return scrape_spec(state)

    def test_returns_spec_items(self):
        result = self._run_with_mocks(_make_state())
        assert "spec_items" in result
        assert len(result["spec_items"]) > 0

    def test_item_schema(self):
        result = self._run_with_mocks(_make_state())
        for item in result["spec_items"]:
            assert "room" in item
            assert "name" in item
            assert "model" in item
            assert "qty" in item
            assert "image_url" in item

    def test_toilet_distributed_to_rooms(self):
        result = self._run_with_mocks(_make_state())
        toilet_items = [i for i in result["spec_items"] if "Toilet" in i["name"] or "Nexus" in i["name"]]
        # Toilets room distributes to bid rooms that have toilet line items
        assert any(i["room"] == "Master Bedroom" for i in toilet_items)

    def test_logs_populated(self):
        result = self._run_with_mocks(_make_state())
        assert result.get("logs")

    def test_expired_token_returns_clear_error(self):
        """401 from auth returns a human-readable error, not a crash."""
        auth_401 = MagicMock()
        auth_401.status_code = 401
        auth_401.raise_for_status.side_effect = Exception("401")

        with patch("nodes.scrape_spec.CACHE_DIR", Path("/tmp/scrape_spec_test_cache")):
            cache = Path("/tmp/scrape_spec_test_cache") / "raw_3408205.json"
            if cache.exists():
                cache.unlink()
            with patch("requests.post", return_value=auth_401):
                result = scrape_spec(_make_state())
        assert "error" in result
        assert "token" in result["error"].lower() or "401" in result["error"]


class TestConvert:
    def test_unknown_room_kept_with_raw_name(self):
        """Rooms not in ROOM_MAP are stored with their raw spec room name for map_rooms AI to translate."""
        all_specs = {"OWNERS SUITE": [{"manufacturerName": "X", "name": "Y", "modelNumber": "Z", "qty": 1, "imageName": ""}]}
        items = _convert(all_specs, [])
        assert len(items) == 1
        assert items[0]["room"] == "OWNERS SUITE"

    def test_known_room_mapped(self):
        all_specs = {"MASTER BATH": [{"manufacturerName": "Brizo", "name": "Faucet", "modelNumber": "ABC", "qty": 1, "imageName": ""}]}
        items = _convert(all_specs, [])
        assert items[0]["room"] == "Master Bedroom"
