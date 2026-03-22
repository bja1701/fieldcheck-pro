"""Tests for graph.py — pipeline wiring, CLI, and error short-circuit."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "nodes"))

from graph import build_graph, _parse_args, _build_initial_state, main


# ── Helpers ───────────────────────────────────────────────────────────────────

_REQUIRED_ARGS = [
    "--spec-url", "https://specbooks.com/v4/especbook/123?token=abc",
    "--bid", "bid.xlsx",
    "--plans", "plans.pdf",
    "--cabinets", "cabinets.pdf",
    "--job-name", "Test Job",
    "--output-dir", "/tmp/out",
]

_EMPTY_STATE = {
    "spec_url": "", "bid_path": "", "plans_path": "", "cabinets_path": "",
    "job_name": "", "output_dir": "", "project_id": "",
    "bid_items": [], "spec_items": [], "rooms": {}, "cabinet_map": {},
    "room_map": {}, "matched_items": [], "review_queue": [], "discrepancies": [],
    "output_data": {}, "logs": [], "error": "",
}

_SUCCESS_STATE = {
    **_EMPTY_STATE,
    "output_data": {"rooms": [{"name": "Kitchen", "items": [{"name": "Sink"}]}]},
}


def _make_node_mock(return_state: dict):
    """Return a mock node function that returns the given state update."""
    return MagicMock(return_value=return_state)


# ── Graph structure ───────────────────────────────────────────────────────────

class TestGraphStructure:
    def test_builds_without_error(self):
        graph = build_graph()
        assert graph is not None

    def test_all_nodes_present(self):
        graph = build_graph()
        nodes = set(graph.get_graph().nodes.keys())
        expected = {
            "parse_bid", "scrape_spec", "extract_plans", "extract_cabinets",
            "map_rooms", "match_items", "generate_output", "publish_to_supabase",
        }
        assert expected.issubset(nodes)


# ── CLI argument parsing ───────────────────────────────────────────────────────

class TestCLIParsing:
    def test_parses_all_required_args(self):
        args = _parse_args(_REQUIRED_ARGS)
        assert args.spec_url == "https://specbooks.com/v4/especbook/123?token=abc"
        assert args.bid == "bid.xlsx"
        assert args.plans == "plans.pdf"
        assert args.cabinets == "cabinets.pdf"
        assert args.job_name == "Test Job"
        assert args.output_dir == "/tmp/out"

    def test_missing_spec_url_raises(self):
        args_without_spec = [a for a in _REQUIRED_ARGS if a not in ("--spec-url", "https://specbooks.com/v4/especbook/123?token=abc")]
        with pytest.raises(SystemExit):
            _parse_args(args_without_spec)

    def test_missing_bid_raises(self):
        args_without_bid = [a for a in _REQUIRED_ARGS if a not in ("--bid", "bid.xlsx")]
        with pytest.raises(SystemExit):
            _parse_args(args_without_bid)

    def test_initial_state_from_args(self):
        args = _parse_args(_REQUIRED_ARGS)
        state = _build_initial_state(args)
        assert state["spec_url"] == args.spec_url
        assert state["bid_path"] == args.bid
        assert state["plans_path"] == args.plans
        assert state["cabinets_path"] == args.cabinets
        assert state["job_name"] == args.job_name
        assert state["output_dir"] == args.output_dir

    def test_initial_state_empty_collections(self):
        args = _parse_args(_REQUIRED_ARGS)
        state = _build_initial_state(args)
        assert state["bid_items"] == []
        assert state["matched_items"] == []
        assert state["rooms"] == {}
        assert state["error"] == ""


# ── Error short-circuit ───────────────────────────────────────────────────────

class TestErrorShortCircuit:
    def _run_with_parse_bid_error(self):
        error_state = {**_EMPTY_STATE, "error": "parse_bid: file not found"}
        success_state = {**_EMPTY_STATE}

        node_mock = _make_node_mock(error_state)
        noop = _make_node_mock(success_state)

        with patch("graph.parse_bid", node_mock), \
             patch("graph.scrape_spec", noop), \
             patch("graph.extract_plans", noop), \
             patch("graph.extract_cabinets", noop), \
             patch("graph.map_rooms", noop), \
             patch("graph.match_items", noop), \
             patch("graph.generate_output", noop), \
             patch("graph.publish_to_supabase", noop):
            pipeline = build_graph()
            return pipeline.invoke(_EMPTY_STATE), noop

    def test_error_halts_pipeline(self):
        result, noop = self._run_with_parse_bid_error()
        assert result.get("error") == "parse_bid: file not found"

    def test_downstream_nodes_skipped_on_error(self):
        _, noop = self._run_with_parse_bid_error()
        noop.assert_not_called()


# ── Success run ───────────────────────────────────────────────────────────────

class TestSuccessRun:
    def _run_all_mocked(self, final_output=None):
        output = final_output or _SUCCESS_STATE["output_data"]
        node_sequence = [
            ("parse_bid", {**_EMPTY_STATE}),
            ("scrape_spec", {**_EMPTY_STATE}),
            ("extract_plans", {**_EMPTY_STATE}),
            ("extract_cabinets", {**_EMPTY_STATE}),
            ("map_rooms", {**_EMPTY_STATE}),
            ("match_items", {**_EMPTY_STATE}),
            ("generate_output", {**_EMPTY_STATE, "output_data": output, "logs": ["done"]}),
            ("publish_to_supabase", {**_EMPTY_STATE, "logs": ["published"]}),
        ]
        patches = {name: patch(f"graph.{name}", _make_node_mock(state))
                   for name, state in node_sequence}
        with patches["parse_bid"], patches["scrape_spec"], patches["extract_plans"], \
             patches["extract_cabinets"], patches["map_rooms"], patches["match_items"], \
             patches["generate_output"], patches["publish_to_supabase"]:
            pipeline = build_graph()
            return pipeline.invoke(_EMPTY_STATE)

    def test_no_error_in_result(self):
        result = self._run_all_mocked()
        assert not result.get("error")

    def test_output_data_present(self):
        result = self._run_all_mocked()
        assert "output_data" in result

    def test_main_returns_zero_on_success(self):
        with patch("graph.build_graph") as mock_build:
            mock_pipeline = MagicMock()
            mock_pipeline.invoke.return_value = _SUCCESS_STATE
            mock_build.return_value = mock_pipeline
            code = main(_REQUIRED_ARGS)
        assert code == 0

    def test_main_returns_one_on_error(self):
        error_result = {**_EMPTY_STATE, "error": "something failed"}
        with patch("graph.build_graph") as mock_build:
            mock_pipeline = MagicMock()
            mock_pipeline.invoke.return_value = error_result
            mock_build.return_value = mock_pipeline
            code = main(_REQUIRED_ARGS)
        assert code == 1
