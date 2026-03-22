# NexusFlow — AI Automation Agency Framework

Code-first AI automation using LangGraph + Python + TDD.

## Quick Start

```bash
# 1. Set your Gemini API key (free at aistudio.google.com)
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY

# 2. Run the demo project
uv run python projects/demo-automation/graph.py

# 3. Run all tests
uv run pytest
```

## How It Works

Every automation is built in 3 phases:

1. **Grill** — Claude interrogates you until `blueprint.md` is complete
2. **TDD Loop** — test → code → run → human checkpoint → repeat
3. **Ship** — tested, working automation deployed for client

## Key Files

| File | Purpose |
|------|---------|
| `DEVELOPER_GUIDE.md` | Rules Claude follows every session |
| `templates/blueprint.md` | Blank requirements template |
| `docs/tools.md` | Free tool reference |
| `library/nodes/` | Reusable node templates |
| `projects/demo-automation/` | Working example to copy |

## Starting a New Automation

Tell Claude: *"I want to build an automation that [vague idea]."*

Claude will follow the Grill Protocol and won't write code until the blueprint is locked.