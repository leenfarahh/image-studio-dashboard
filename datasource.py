"""Fetch layer: pulls raw rows from the tool's Supabase project."""
from datetime import datetime

import requests

import config


def _headers(key):
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def _paginated_get(base_url, key, path, params, page_size=1000):
    base = f"{base_url.rstrip('/')}/rest/v1/{path}"
    rows, offset = [], 0
    while True:
        headers = dict(_headers(key))
        headers["Range-Unit"] = "items"
        headers["Range"] = f"{offset}-{offset + page_size - 1}"
        resp = requests.get(base, headers=headers, params=params, timeout=30)
        if resp.status_code not in (200, 206):
            raise RuntimeError(
                f"Supabase request to {path} failed ({resp.status_code}): {resp.text[:400]}"
            )
        batch = resp.json()
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def parse_ts(value):
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


# ------------------------------------------------------------------
# Tool project
# ------------------------------------------------------------------
def fetch_tool_events(since):
    """All generation attempts, successes AND failures.

    Failures are kept deliberately: reliability is an adoption driver, and
    filtering on success=true makes every error invisible.
    """
    rows = _paginated_get(
        config.TOOL_SUPABASE_URL,
        config.TOOL_SUPABASE_API_KEY,
        config.EVENTS_TABLE,
        {
            "select": "user_id,provider,model,operation,success,error_code,latency_ms,created_at,image_id,conversation_id",
            "created_at": f"gte.{since.isoformat()}",
            "order": "created_at.asc",
        },
    )
    events = []
    for r in rows:
        provider = config.normalize_provider(r.get("provider"))
        operation = config.normalize_operation(r.get("operation"))
        ts = parse_ts(r.get("created_at"))
        if not provider or not operation or ts is None:
            continue
        events.append({
            "provider": provider,
            "operation": operation,
            "user_id": r.get("user_id"),
            "model": r.get("model"),
            "success": bool(r.get("success")),
            "error_code": r.get("error_code"),
            "latency_ms": r.get("latency_ms"),
            "conversation_id": r.get("conversation_id"),
            "image_id": r.get("image_id"),
            "ts": ts,
        })
    return events


def fetch_images(since):
    rows = _paginated_get(
        config.TOOL_SUPABASE_URL,
        config.TOOL_SUPABASE_API_KEY,
        config.IMAGES_TABLE,
        {
            "select": "id,user_id,provider,model,operation,parent_image_id,prompt,saved,created_at",
            "created_at": f"gte.{since.isoformat()}",
            "order": "created_at.asc",
        },
    )
    images = []
    for r in rows:
        ts = parse_ts(r.get("created_at"))
        if ts is None:
            continue
        images.append({
            "id": r.get("id"),
            "user_id": r.get("user_id"),
            "provider": config.normalize_provider(r.get("provider")),
            "operation": config.normalize_operation(r.get("operation")),
            # The prompt is the only field that can tie a retry to the attempt
            # it replaced, so retry detection depends on selecting it.
            "prompt": (r.get("prompt") or "").strip(),
            "parent_image_id": r.get("parent_image_id"),
            "saved": bool(r.get("saved")),
            "ts": ts,
        })
    return images


def fetch_profiles():
    """The adoption denominator: people provisioned on the tool.

    This still returns the per-tool profiles (used for identity mapping). The
    overall adoption denominator can be supplied separately from Odoo (headcount)
    and is attached to the raw payload by load_all.
    """
    rows = _paginated_get(
        config.TOOL_SUPABASE_URL,
        config.TOOL_SUPABASE_API_KEY,
        config.PROFILES_TABLE,
        {"select": "id,email,full_name,is_active,role,created_at,last_seen_at"},
    )
    return [{
        "id": r.get("id"),
        "email": (r.get("email") or "").strip().lower(),
        "full_name": r.get("full_name") or r.get("email") or "Unknown",
        "is_active": bool(r.get("is_active")),
        "role": r.get("role"),
        "created_at": parse_ts(r.get("created_at")),
    } for r in rows]


def fetch_headcount_from_odoo():
    """Query Odoo for the headcount of the configured department.

    Tries a best-effort REST call. The exact Odoo API shape may vary between
    deployments; this supports common patterns:
      - If the endpoint returns a list of employee objects, the length is used.
      - If the endpoint returns an object with a 'count' or 'total' field, that
        value is used.

    Returns an int (>=0) on success or None if no Odoo config is present or the
    call/response could not be understood.
    """
    if not config.ODOO_API_URL or not config.ODOO_API_KEY:
        return None

    url = config.ODOO_API_URL.rstrip('/') + '/employees'
    headers = {"Authorization": f"Bearer {config.ODOO_API_KEY}"}
    params = {"department": config.ODOO_DEPARTMENT}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()
        # List response -> count length
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            for key in ("count", "total", "size", "employees_count"):
                if key in data and isinstance(data[key], int):
                    return data[key]
            # Maybe employees under a key
            for key in ("employees", "results", "data"):
                if key in data and isinstance(data[key], list):
                    return len(data[key])
        # Unknown shape
        return None
    except Exception:
        return None


def load_all(since):
    return {
        "tool_events": fetch_tool_events(since),
        "images": fetch_images(since),
        "profiles": fetch_profiles(),
        "headcount": fetch_headcount_from_odoo(),
    }
