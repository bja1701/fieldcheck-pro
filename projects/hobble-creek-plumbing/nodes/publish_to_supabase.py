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

import json
import os

from state import FieldCheckState

SUPABASE_URL = "https://ftidlgjmtiyuxycaacob.supabase.co"


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
