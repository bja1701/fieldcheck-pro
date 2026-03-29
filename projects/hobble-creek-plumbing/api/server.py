"""
FieldCheck Pro — Local API server.

Wraps the LangGraph pipeline and exposes two endpoints the Vercel frontend calls:

  POST /api/run-pipeline   — download files, kick off pipeline in background thread
  GET  /api/project-status — poll pipeline progress by project_id

Start with:
  uv run uvicorn projects.hobble-creek-plumbing.api.server:app --host 0.0.0.0 --port 8000 --reload

Or use api/start.sh which also launches the Cloudflare tunnel.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Path bootstrap so pipeline imports (graph, state, nodes.*) resolve ────────
PIPELINE_DIR = Path(__file__).parent.parent  # hobble-creek-plumbing/
sys.path.insert(0, str(PIPELINE_DIR))

from graph import build_graph  # noqa: E402  (import after sys.path patch)
from state import FieldCheckState  # noqa: E402

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="FieldCheck Pro API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory job state ───────────────────────────────────────────────────────
# Keyed by project_id (Supabase UUID string).
# Shape mirrors what job.html expects from /api/project-status.
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()

_STEP_LABELS = [
    "Parsing bid sheet",
    "Scraping spec book",
    "Extracting plans",
    "Extracting cabinet drawings",
    "Mapping rooms",
    "Matching items",
    "Generating output",
    "Publishing to Supabase",
]
_TOTAL_STEPS = len(_STEP_LABELS)

# Compiled pipeline — built once at startup, reused for every run.
_pipeline = build_graph()


def _make_status(
    status: str = "pending",
    step: int = 0,
    step_label: str = "Queued",
) -> dict[str, Any]:
    return {
        "status": status,
        "step": step,
        "step_label": step_label,
        "total_steps": _TOTAL_STEPS,
        "log": [],
        "error": None,
    }


# ── Request schema ────────────────────────────────────────────────────────────
class RunPipelineRequest(BaseModel):
    project_id: str
    project_name: str
    spec_url: str
    bid_url: str
    plans_url: str
    cabinets_url: str
    access_token: str = ""


# ── Helpers ───────────────────────────────────────────────────────────────────
def _download(client: httpx.Client, url: str, dest: Path) -> None:
    resp = client.get(url)
    resp.raise_for_status()
    dest.write_bytes(resp.content)


def _run_pipeline(req: RunPipelineRequest, tmp_dir: Path) -> None:
    """Background thread: download files, run pipeline, update _jobs."""
    pid = req.project_id

    def _log(msg: str) -> None:
        with _jobs_lock:
            _jobs[pid]["log"].append(msg)

    def _set(key: str, value: Any) -> None:
        with _jobs_lock:
            _jobs[pid][key] = value

    try:
        # Download all three files in parallel
        _log("Downloading input files…")
        downloads = [
            (req.bid_url,      tmp_dir / "bid.xlsx"),
            (req.plans_url,    tmp_dir / "plans.pdf"),
            (req.cabinets_url, tmp_dir / "cabinets.pdf"),
        ]
        with httpx.Client(follow_redirects=True, timeout=60) as client:
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = [pool.submit(_download, client, url, dest) for url, dest in downloads]
                for f in futures:
                    f.result()  # raises on any download failure

        bid_path, plans_path, cabinets_path = [dest for _, dest in downloads]
        output_dir = tmp_dir / "output"
        output_dir.mkdir(exist_ok=True)

        _log("Files ready. Starting pipeline…")
        with _jobs_lock:
            _jobs[pid].update(step=0, step_label=_STEP_LABELS[0])

        initial = FieldCheckState(
            spec_url=req.spec_url,
            bid_path=str(bid_path),
            plans_path=str(plans_path),
            cabinets_path=str(cabinets_path),
            job_name=req.project_name,
            output_dir=str(output_dir),
            project_id=req.project_id,
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

        result = _pipeline.invoke(initial)

        if result.get("error"):
            with _jobs_lock:
                _jobs[pid].update(status="error", error=result["error"])
            _log(f"Pipeline error: {result['error']}")
            return

        for entry in result.get("logs", []):
            _log(entry)

        with _jobs_lock:
            _jobs[pid].update(status="complete", step=_TOTAL_STEPS, step_label="Done", error=None)
        _log("Pipeline complete.")

    except Exception as exc:
        with _jobs_lock:
            _jobs[pid].update(status="error", error=str(exc))
        _log(f"Server error: {exc}")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.post("/api/run-pipeline")
async def run_pipeline(req: RunPipelineRequest) -> dict:
    pid = req.project_id

    with _jobs_lock:
        existing = _jobs.get(pid, {})
        if existing.get("status") == "processing":
            raise HTTPException(status_code=409, detail="Pipeline already running for this project.")
        _jobs[pid] = _make_status(status="processing", step=0, step_label=_STEP_LABELS[0])

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"fcp_{pid}_"))

    threading.Thread(
        target=_run_pipeline,
        args=(req, tmp_dir),
        daemon=True,
        name=f"pipeline-{pid}",
    ).start()

    return {"status": "ok", "project_id": pid}


@app.get("/api/project-status")
async def project_status(id: str) -> dict:
    with _jobs_lock:
        return dict(_jobs.get(id) or _make_status())
