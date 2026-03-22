"""
State Schema Template — copy and modify for each project.

LangGraph passes this dict between every node.
Only include fields your workflow actually needs.
All fields must have a default or be provided at graph invocation.
"""

from typing import TypedDict, Annotated
import operator


class BaseState(TypedDict):
    """
    Minimal base state. Add your project-specific fields below.

    Tips:
    - Use Annotated[list, operator.add] for fields that nodes APPEND to
      (e.g. messages, logs) so LangGraph merges them automatically.
    - Use plain types for fields that nodes OVERWRITE.
    """

    # Input provided when you invoke the graph
    user_input: str

    # Running log — uses operator.add so each node can append without overwriting
    logs: Annotated[list[str], operator.add]

    # Final output written by the last node
    output: str

    # Workflow status: "running" | "waiting_for_human" | "done" | "error"
    status: str

    # Error message if something fails
    error: str
