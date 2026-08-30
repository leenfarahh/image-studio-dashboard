"""Fetch layer: pulls raw rows from the tool project and the standalone project."""
import sqlite3
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
            "source": "tool",
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
            "select": "id,user_id,provider,model,operation,parent_image_id,saved,created_at",
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
            "parent_image_id": r.get("parent_image_id"),
            "saved": bool(r.get("saved")),
            "ts": ts,
        })
    return images


def fetch_profiles():
    """The adoption denominator: people provisioned on the tool."""
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


# ------------------------------------------------------------------
# Standalone project (direct ChatGPT / Gemini use, outside the tool)
# ------------------------------------------------------------------
def fetch_standalone_events(since):
    if config.standalone_configured():
        rows = _paginated_get(
            config.STANDALONE_SUPABASE_URL,
            config.STANDALONE_SUPABASE_SERVICE_ROLE_KEY,
            config.STANDALONE_TABLE,
            {
                "select": "provider,user_id,operation,model,source,created_at",
                "created_at": f"gte.{since.isoformat()}",
                "order": "created_at.asc",
            },
        )
    else:
        rows = _read_sqlite_events()

    events = []
    for r in rows:
        provider = config.normalize_provider(r.get("provider"))
        operation = config.normalize_operation(r.get("operation"))
        ts = parse_ts(r.get("created_at"))
        if not provider or not operation or ts is None:
            continue
        events.append({
            "source": "direct",
            "provider": provider,
            "operation": operation,
            "user_id": (r.get("user_id") or "").strip().lower(),
            "model": r.get("model"),
            "origin": r.get("source"),
            "success": True,
            "latency_ms": None,
            "ts": ts,
        })
    return events


def _read_sqlite_events():
    conn = sqlite3.connect(config.STANDALONE_DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT provider, user_id, operation, model, source, created_at "
            "FROM standalone_events ORDER BY created_at ASC"
        )
        cols = ["provider", "user_id", "operation", "model", "source", "created_at"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def load_all(since):
    return {
        "tool_events": fetch_tool_events(since),
        "images": fetch_images(since),
        "profiles": fetch_profiles(),
        "standalone_events": fetch_standalone_events(since),
    }
