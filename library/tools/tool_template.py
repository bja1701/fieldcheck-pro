"""
Tool Template — copy this when creating a LangChain/LangGraph tool.

Tools are functions the LLM can call inside a node.
They wrap external APIs, databases, web search, etc.

Naming convention: <action>_<resource>.py (e.g. search_web.py, read_google_sheet.py)
"""

from langchain_core.tools import tool


@tool
def example_tool(query: str) -> str:
    """
    Describe what this tool does in ONE clear sentence.
    The LLM uses this docstring to decide when to call the tool.

    Args:
        query: The input the LLM passes to this tool.

    Returns:
        A string result the LLM can read and act on.
    """
    # --- Your tool logic goes here ---
    # Example: call an API, query a DB, read a file, etc.
    result = f"Tool received: {query}"
    # ---------------------------------

    return result
