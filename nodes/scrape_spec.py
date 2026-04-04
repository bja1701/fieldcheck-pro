"""
Node 2: scrape_spec
Authenticates with specbooks.com API and fetches all fixture items per room.

Spec book URL format:
  https://specbooks.com/v4/especbook/{ID}?token={TOKEN}

Output state keys updated:
  spec_items: list of {room, name, model, qty, image_url}
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from state import FieldCheckState

AUTH_URL = "https://specbooks-api.specbooks.cloud/v1/auth/especbooks"
API_BASE = "https://api.marketplace.specbooks.cloud"
ASSETS_BASE = "https://assets.specbooks.cloud/"
CACHE_DIR = Path("projects/hobble-creek-plumbing/cache")

# Map spec book room names (upper) → bid sheet room names
# Extend this per job via the job config if needed
ROOM_MAP: dict[str, str] = {
    "KITCHEN": "Main floor",
    "MUD ROOM": "Main floor",
    "1/2 BATH 1": "1/2  Bath 1",
    "1/2 BATH 2": "1/2  Bath 2",
    "MASTER BATH": "Master Bedroom",
    "GOLF SIMULATOR": "Basement",
    "BATH 2": "Bathroom 2",
    "BATH 3": "Bathroom 3",
    "BATH 4": "Bathroom 4",
    "UPPER LAUNDRY": "Upper Floor",
    "BATH 5": "Bathroom 5",
    "REC ROOM": "Basement",
    "TOILETS": "__TOILETS__",  # handled specially
}

# Rooms that have toilets per bid — used to distribute spec toilet items
TOILET_ROOMS: list[tuple[str, int]] = [
    ("Master Bedroom", 1),
    ("1/2  Bath 1", 1),
    ("1/2  Bath 2", 1),
    ("Bathroom 2", 1),
    ("Bathroom 3", 1),
    ("Bathroom 4", 2),
    ("Bathroom 5", 1),
]


def _extract_id_token(url: str) -> tuple[str, str]:
    m = re.search(r"/especbook/(\d+)", url)
    if not m:
        raise ValueError(f"Cannot find specbook ID in URL: {url}")
    spec_id = m.group(1)
    qs = parse_qs(urlparse(url).query)
    token = qs.get("token", [""])[0]
    if not token:
        raise ValueError(f"No token= found in URL: {url}")
    return spec_id, token


def _cache_path(spec_id: str) -> Path:
    return CACHE_DIR / f"raw_{spec_id}.json"


def _auth(spec_id: str, token: str) -> tuple[str, str]:
    import requests
    resp = requests.post(AUTH_URL, json={"token": token, "specbookId": spec_id}, timeout=60)
    if resp.status_code == 401:
        raise RuntimeError(
            "specbooks.com auth failed (401). The token may have expired or not yet loaded. "
            "Open the spec book URL in a browser, wait for it to fully load (watch for the "
            "spinner to stop), then copy the URL from the address bar. "
            "Copying the URL too early can capture a token before it activates."
        )
    resp.raise_for_status()
    data = resp.json()
    jwt = data.get("data") or data.get("access_token") or data.get("token")
    if not jwt:
        raise RuntimeError(f"No access_token in auth response: {list(data.keys())}")
    import base64
    payload_b64 = jwt.split(".")[1]
    payload_b64 += "=" * (4 - len(payload_b64) % 4)
    payload = json.loads(base64.b64decode(payload_b64))
    return jwt, str(payload.get("sub", ""))


def _fetch_all(spec_id: str, user_id: str, jwt: str) -> dict[str, list[dict]]:
    import requests
    headers = {"Authorization": f"Bearer {jwt}", "Accept": "application/json"}
    base = f"{API_BASE}/v4/user/{user_id}/specbook/{spec_id}"

    cats_resp = requests.get(f"{base}/categories", headers=headers, timeout=60)
    cats_resp.raise_for_status()
    cats_data = cats_resp.json()
    categories = cats_data.get("data", cats_data) if isinstance(cats_data, dict) else cats_data

    all_specs: dict[str, list[dict]] = {}
    for cat in categories:
        cat_name = (cat.get("name") or "").upper().strip()
        cat_id = cat.get("id") or cat.get("categoryID")
        if not cat_id or not cat_name:
            continue
        page = 1
        while True:
            specs_resp = requests.get(
                f"{base}/specs",
                params={"categoryID": cat_id, "showPagination": "true", "page": page},
                headers=headers,
                timeout=60,
            )
            specs_resp.raise_for_status()
            body = specs_resp.json()
            items = body.get("specs", body.get("data", [])) if isinstance(body, dict) else body
            if not items:
                break
            all_specs.setdefault(cat_name, []).extend(items)
            pagination = body.get("pagination", body.get("meta", {})) if isinstance(body, dict) else {}
            last_page = pagination.get("lastPage", pagination.get("last_page", 1))
            if page >= last_page:
                break
            page += 1

    return all_specs


def _convert(all_specs: dict[str, list[dict]], bid_items: list[dict]) -> list[dict]:
    bid_toilet_rooms = {
        item["room"] for item in bid_items
        if "toilet" in item.get("name", "").lower()
    }
    spec_items: list[dict] = []

    for spec_room, items in all_specs.items():
        bid_room = ROOM_MAP.get(spec_room)

        if bid_room == "__TOILETS__":
            for room_name, qty in TOILET_ROOMS:
                if room_name in bid_toilet_rooms:
                    for raw in items:
                        spec_items.append(_to_item(raw, room_name, qty_override=qty))
            continue

        if bid_room is None:
            # Not in hardcoded map — store with raw spec room name for map_rooms AI to translate
            for raw in items:
                spec_items.append(_to_item(raw, spec_room))
            continue

        for raw in items:
            spec_items.append(_to_item(raw, bid_room))

    return spec_items


def _to_item(raw: dict, room: str, qty_override: int | None = None) -> dict:
    img = raw.get("imageName", "")
    brand = raw.get("manufacturerName", "") or ""
    name = raw.get("name", "") or ""
    return {
        "room": room,
        "name": f"{brand} {name}".strip(),
        "model": raw.get("modelNumber", "") or "",
        "qty": qty_override if qty_override is not None else int(raw.get("qty", 1)),
        "image_url": (ASSETS_BASE + img) if img else "",
    }


def _unique_filename(cdn_url: str) -> str:
    """Build a unique local filename for a Specbooks CDN image URL.

    Specbooks URLs follow: .../spec/{specID}/image/default.{ext}
    All images are named 'default.png', so we use the specID to avoid
    every item mapping to the same local file.
    """
    ext = cdn_url.rsplit(".", 1)[-1].split("?")[0].lower()
    if not ext or len(ext) > 4:
        ext = "jpg"
    m = re.search(r"/spec/(\d+)/", cdn_url)
    if m:
        return f"{m.group(1)}.{ext}"
    # Fallback: hash the URL for uniqueness
    return hashlib.md5(cdn_url.encode()).hexdigest()[:16] + "." + ext


def _download_images(spec_items: list[dict], output_dir: str) -> list[dict]:
    """Download spec images to {output_dir}/spec_images/, update image_url to local path.

    Skips files that already exist on disk so re-runs are fast.
    Falls back to CDN URL on download failure — never aborts the pipeline.
    """
    import requests as _req
    images_dir = Path(output_dir) / "spec_images"
    images_dir.mkdir(parents=True, exist_ok=True)

    result = []
    for item in spec_items:
        cdn_url = item.get("image_url", "")
        if not cdn_url:
            result.append(item)
            continue
        filename = _unique_filename(cdn_url)
        local = images_dir / filename
        if not local.exists():
            try:
                resp = _req.get(cdn_url, timeout=30)
                resp.raise_for_status()
                local.write_bytes(resp.content)
            except Exception as e:
                print(f"  [scrape_spec] Warning: image download failed for {filename}: {e}")
                result.append(item)
                continue
        result.append({**item, "image_url": f"spec_images/{filename}"})
    return result


def scrape_spec(state: FieldCheckState) -> dict:
    url = state["spec_url"]
    bid_items = state.get("bid_items", [])
    output_dir = state.get("output_dir", "")

    try:
        spec_id, token = _extract_id_token(url)
    except ValueError as e:
        return {"error": str(e), "spec_items": []}

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = _cache_path(spec_id)

    if cache.exists():
        print(f"  [scrape_spec] Cache hit: {cache}")
        all_specs = json.loads(cache.read_text())
    else:
        try:
            jwt, user_id = _auth(spec_id, token)
            all_specs = _fetch_all(spec_id, user_id, jwt)
            cache.write_text(json.dumps(all_specs, indent=2))
        except Exception as e:
            return {"error": f"scrape_spec failed: {e}", "spec_items": []}

    spec_items = _convert(all_specs, bid_items)

    if not spec_items:
        return {
            "error": "scrape_spec returned 0 items — check ROOM_MAP or token validity",
            "spec_items": [],
        }

    # image_url is the full Specbooks CDN URL — keep it as-is so it works
    # from Vercel and any browser. Local downloading breaks Vercel deployments.

    return {
        "spec_items": spec_items,
        "logs": [f"scrape_spec: {len(spec_items)} items from specbook {spec_id}"],
    }
