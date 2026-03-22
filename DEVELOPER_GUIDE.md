# NexusFlow Developer Guide

Claude follows this guide every session. Load it at the start of each conversation.

---

## 1. The Grill Protocol (No Code Until Blueprint Is Done)

When Brighton gives a vague idea, go through this interrogation BEFORE writing code:

1. **Trigger**: What exactly starts the process?
2. **Input data**: What does the incoming data look like? Paste a sample.
3. **Step-by-step logic**: Walk me through every step in plain English.
4. **Output**: What does success look like? What is produced?
5. **External services**: Every API, database, or service it touches.
6. **Edge cases**: What should happen when X fails?
7. **Error handling**: Retry? Notify? Log? Abort?
8. **Success metric**: How do we prove it worked programmatically?

**Rule:** Do not write a single line of code until `blueprint.md` is filled out and Brighton approves it.

Template: `templates/blueprint.md`

---

## 2. The TDD Loop (Every Chunk)

For each chunk of the automation:

```
1. Write test file:  tests/test_chunk_X.py
2. Write node logic: chunk_X.py
3. Run: uv run pytest tests/test_chunk_X.py -v
4. Fix until all tests pass
5. Notify Brighton: "Chunk X done — tests passing. Proceed to Chunk X+1?"
6. Wait for approval before moving on
```

**Rule:** No code without a preceding test. No exceptions.

---

## 3. Library Recall (Reuse Before Reinventing)

Before writing any new node, tool, or state schema:

```
1. Search library/nodes/ for similar functionality
2. Search library/tools/ for reusable API wrappers
3. Check library/states/ for matching state shapes
4. If a match exists, copy it and modify — don't start from scratch
```

**Quick search:**
```bash
# Find nodes related to "email"
grep -rl "email" library/

# List all available node templates
ls library/nodes/

# Find tools for a specific API
ls library/tools/
```

---

## 4. Free Tool Priority

Always check `docs/tools.md` before picking a library or API.

Priority: **Free → Easy → Cheap (if free option is terrible)**

Default LLM: **Gemini 2.0 Flash** (`gemini-2.0-flash` via `langchain-google-genai`)

---

## 5. Human-in-the-Loop Checkpoints

LangGraph supports pausing execution for Brighton to review before continuing.

**How to add a breakpoint:**
```python
graph = builder.compile(
    checkpointer=MemorySaver(),
    interrupt_before=["node_that_requires_approval"]
)
```

**How to resume after Brighton approves:**
```python
# Resume the paused graph with the same thread_id
graph.invoke(None, config={"configurable": {"thread_id": "your-thread-id"}})
```

Use this pattern for nodes that:
- Send emails or messages to real people
- Write to production databases
- Make irreversible API calls
- Cost money

---

## 6. Project Structure

```
nexusflow_builds/
├── library/
│   ├── nodes/        ← Reusable node functions (copy & modify)
│   ├── states/       ← Reusable state schemas
│   └── tools/        ← Reusable LangChain tools (API wrappers)
├── projects/
│   └── [client-name]/
│       ├── blueprint.md   ← Filled-out blueprint (grill output)
│       ├── graph.py       ← The LangGraph state machine
│       └── tests/         ← One test file per node/chunk
├── templates/
│   └── blueprint.md       ← Blank blueprint template
├── docs/
│   └── tools.md           ← Free tool reference
├── .env                   ← Secrets (never commit)
├── .env.example           ← Safe template to commit
└── DEVELOPER_GUIDE.md     ← This file
```

---

## 7. Starting a New Client Project

```bash
# 1. Copy the demo project as a starting point
cp -r projects/demo-automation projects/[client-name]

# 2. Fill out the blueprint
cp templates/blueprint.md projects/[client-name]/blueprint.md
# Then fill it out with Claude's help (Grill Protocol)

# 3. Build chunk by chunk with TDD
# (see Section 2)
```

---

## 8. Running Tests

```bash
# Run all tests
uv run pytest

# Run tests for one project
uv run pytest projects/[client-name]/tests/ -v

# Run library template tests
uv run pytest library/ -v
```

---

## 9. Environment Setup

```bash
# Activate venv (if needed)
source .venv/bin/activate

# Set your API key (one time, in .env file)
echo "GOOGLE_API_KEY=your_key_here" >> .env
```

Get a free Gemini API key: https://aistudio.google.com/apikey
