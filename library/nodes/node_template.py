"""
Node Template — copy this file when creating a new LangGraph node.

A node is a Python function that:
  - Receives the current graph state
  - Does one specific thing (fetch, transform, decide, call API, etc.)
  - Returns a dict of state keys to update

Naming convention: <verb>_<noun>.py  (e.g. fetch_emails.py, summarize_text.py)
"""

from typing import TypedDict


# --- State type (import from your project's state file in real use) ---
class ExampleState(TypedDict):
    input_text: str
    output_text: str
    status: str


# --- The node function ---
def process_text(state: ExampleState) -> dict:
    """
    Example node: transforms input_text to uppercase.

    Replace this logic with your actual node behavior.
    Always return only the keys you want to UPDATE in the state.
    """
    raw = state["input_text"]

    # --- Your logic goes here ---
    result = raw.upper()
    # ----------------------------

    return {
        "output_text": result,
        "status": "done",
    }
