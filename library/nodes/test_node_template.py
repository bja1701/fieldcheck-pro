"""
Unit tests for node_template.py — this is the TDD test file pattern.

Write these BEFORE writing the node logic.
Each test covers one behavior or edge case.
"""

import pytest
from node_template import process_text, ExampleState


class TestProcessText:
    def test_uppercases_normal_input(self):
        state: ExampleState = {"input_text": "hello world", "output_text": "", "status": ""}
        result = process_text(state)
        assert result["output_text"] == "HELLO WORLD"

    def test_status_set_to_done(self):
        state: ExampleState = {"input_text": "anything", "output_text": "", "status": ""}
        result = process_text(state)
        assert result["status"] == "done"

    def test_empty_string_input(self):
        state: ExampleState = {"input_text": "", "output_text": "", "status": ""}
        result = process_text(state)
        assert result["output_text"] == ""

    def test_returns_only_updated_keys(self):
        """Node should return a dict, not the full state."""
        state: ExampleState = {"input_text": "test", "output_text": "", "status": ""}
        result = process_text(state)
        assert isinstance(result, dict)
        assert "output_text" in result
        assert "status" in result
