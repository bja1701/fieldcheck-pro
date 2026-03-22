"""
FieldCheck Pro — LangGraph pipeline entry point.

Usage:
    uv run python projects/hobble-creek-plumbing/graph.py \
        --spec-url "https://specbooks.com/v4/especbook/3408205?token=abc123" \
        --bid "Baker_Bid.xlsx" \
        --plans "plans.pdf" \
        --cabinets "cabinets.pdf" \
        --job-name "Baker Residence" \
        --output-dir "/home/frank/PAI/fieldcheck-pro" \
        --project-id "096048b7-c3fd-4b5f-b072-06c620c17fd8"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from langgraph.graph import END, StateGraph

from nodes.extract_cabinets import extract_cabinets
from nodes.extract_plans import extract_plans
from nodes.generate_output import generate_output
from nodes.map_rooms import map_rooms
from nodes.match_items import match_items
from nodes.parse_bid import parse_bid
from nodes.publish_to_supabase import publish_to_supabase
from nodes.scrape_spec import scrape_spec
from state import FieldCheckState


def _route(next_node: str):
    """Return a conditional-edge function that halts on error, else goes to next_node."""
    def _fn(state: FieldCheckState) -> str:
        return END if state.get("error") else next_node
    return _fn


def build_graph():
    """Compile and return the FieldCheck Pro StateGraph."""
    g = StateGraph(FieldCheckState)

    g.add_node("parse_bid", parse_bid)
    g.add_node("scrape_spec", scrape_spec)
    g.add_node("extract_plans", extract_plans)
    g.add_node("extract_cabinets", extract_cabinets)
    g.add_node("map_rooms", map_rooms)
    g.add_node("match_items", match_items)
    g.add_node("generate_output", generate_output)
    g.add_node("publish_to_supabase", publish_to_supabase)

    g.set_entry_point("parse_bid")
    g.add_conditional_edges("parse_bid", _route("scrape_spec"))
    g.add_conditional_edges("scrape_spec", _route("extract_plans"))
    g.add_conditional_edges("extract_plans", _route("extract_cabinets"))
    g.add_conditional_edges("extract_cabinets", _route("map_rooms"))
    g.add_conditional_edges("map_rooms", _route("match_items"))
    g.add_conditional_edges("match_items", _route("generate_output"))
    g.add_conditional_edges("generate_output", _route("publish_to_supabase"))
    g.add_edge("publish_to_supabase", END)

    return g.compile()


def _build_initial_state(args: argparse.Namespace) -> FieldCheckState:
    return FieldCheckState(
        spec_url=args.spec_url,
        bid_path=args.bid,
        plans_path=args.plans,
        cabinets_path=args.cabinets,
        job_name=args.job_name,
        output_dir=args.output_dir,
        project_id=getattr(args, "project_id", "") or "",
        bid_items=[],
        spec_items=[],
        rooms={},
        cabinet_map={},
        room_map={},
        matched_items=[],
        review_queue=[],
        discrepancies=[],
        output_data={},
        logs=[],
        error="",
    )


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FieldCheck Pro — plumbing bid verification pipeline")
    parser.add_argument("--spec-url", required=True, help="specbooks.com URL with ?token=")
    parser.add_argument("--bid", required=True, help="Path to bid sheet CSV or XLSX")
    parser.add_argument("--plans", required=True, help="Path to house plans PDF")
    parser.add_argument("--cabinets", required=True, help="Path to cabinet drawings PDF")
    parser.add_argument("--job-name", required=True, help='Human-readable job name (e.g. "Baker Residence")')
    parser.add_argument("--output-dir", required=True, help="Directory for output files (data.js, images)")
    parser.add_argument("--project-id", default="", help="Supabase project UUID — publishes output_data when provided")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    pipeline = build_graph()
    state = _build_initial_state(args)

    result = pipeline.invoke(state)

    if result.get("error"):
        print(f"ERROR: {result['error']}", file=sys.stderr)
        return 1

    rooms = result.get("output_data", {}).get("rooms", [])
    items = sum(len(r.get("items", [])) for r in rooms)
    review = len(result.get("review_queue", []))
    published = bool(getattr(args, "project_id", ""))
    print(f"Done: {len(rooms)} rooms, {items} items written to {args.output_dir}/data.js")
    if published:
        print(f"Published to Supabase project {args.project_id}")
    if review:
        print(f"Review queue: {review} low-confidence matches need attention")
    return 0


if __name__ == "__main__":
    sys.exit(main())
