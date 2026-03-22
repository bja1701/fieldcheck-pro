"""
Node 8: publish_to_supabase
Writes output_data (JOB_DATA) into the Supabase projects.generated_data column
and sets project status to "complete".

Requires:
  SUPABASE_URL            in env (or hardcoded fallback)
  SUPABASE_SERVICE_ROLE   in env  ← service role key, bypasses RLS

Non-fatal: if project_id is not set or creds are missing, logs a warning and
continues — the pipeline still writes data.js locally.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

from state import FieldCheckState

SUPABASE_URL = "https://ftidlgjmtiyuxycaacob.supabase.co"


def _upload_images(output_data: dict, output_dir: str, project_id: str,
                   supabase_url: str, service_key: str) -> dict:
    """Upload local images to Supabase Storage and replace paths with public URLs."""
    import requests

    data = copy.deepcopy(output_data)
    bucket = "project-images"

    def _upload_file(relative_path: str) -> str:
        """Upload a single file, return public URL or original path on failure."""
        try:
            file_path = Path(output_dir) / relative_path
            if not file_path.is_file():
                return relative_path

            storage_path = f"{project_id}/{relative_path}"
            upload_url = f"{supabase_url}/storage/v1/object/{bucket}/{storage_path}"

            with open(file_path, "rb") as f:
                resp = requests.post(
                    upload_url,
                    headers={
                        "apikey": service_key,
                        "Authorization": f"Bearer {service_key}",
                        "x-upsert": "true",
                    },
                    files={"file": (file_path.name, f)},
                    timeout=30,
                )
            if resp.ok:
                return f"{supabase_url}/storage/v1/object/public/{bucket}/{storage_path}"
            return relative_path
        except Exception:
            return relative_path

    # Replace paths in rooms[].cabinetImages[]
    for room in data.get("rooms", []):
        images = room.get("cabinetImages", [])
        for i, img in enumerate(images):
            if isinstance(img, str) and not img.startswith("http"):
                images[i] = _upload_file(img)

    # Replace paths in planNavigation.{floor}.images[]
    plan_nav = data.get("planNavigation", {})
    for floor_key, floor_data in plan_nav.items():
        if not isinstance(floor_data, dict):
            continue
        images = floor_data.get("images", [])
        for i, img in enumerate(images):
            if isinstance(img, str) and not img.startswith("http"):
                images[i] = _upload_file(img)

    return data


def publish_to_supabase(state: FieldCheckState) -> dict:
    project_id = state.get("project_id", "")
    output_data = state.get("output_data", {})

    if not project_id:
        return {"logs": ["publish_to_supabase: no project_id set — skipping Supabase publish"]}

    service_key = os.environ.get("SUPABASE_SERVICE_ROLE", "")
    if not service_key:
        return {"logs": ["publish_to_supabase: SUPABASE_SERVICE_ROLE not set — skipping"]}

    if not output_data:
        return {"error": "publish_to_supabase: output_data is empty — cannot publish"}

    output_dir = state.get("output_dir", "")
    if output_dir:
        output_data = _upload_images(output_data, output_dir, project_id,
                                     SUPABASE_URL, service_key)

    import requests
    url = f"{SUPABASE_URL}/rest/v1/projects?id=eq.{project_id}"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    payload = {
        "generated_data": output_data,
        "status": "complete",
    }

    try:
        resp = requests.patch(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        # Non-fatal — log and continue
        return {"logs": [f"publish_to_supabase: WARNING — publish failed: {e}"]}

    return {"logs": [f"publish_to_supabase: published to project {project_id}"]}
