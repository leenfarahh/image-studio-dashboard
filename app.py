"""Ingestion + refresh service for the adoption dashboards.

Endpoints
    POST /log-standalone     one direct (outside-the-tool) usage event
    POST /import-standalone  bulk CSV import from a vendor admin export
    POST /refresh            re-pull everything and rebuild the three dashboards
    GET  /dashboard/<name>   serve a rendered dashboard
    GET  /dashboard_data.json
    GET  /health

Writes to public.standalone_usage_events in the standalone Supabase project,
falling back to a local SQLite file when that project is not configured.
"""
import csv
import hashlib
import io
import json
import os
import secrets
import sqlite3
import threading
import time
from datetime import date, datetime, timezone

import requests
from flask import Flask, abort, jsonify, make_response, request, send_from_directory

import config
import image_generation_dashboard_sync as sync

app = Flask(__name__)

VALID_OPERATIONS = {"generate", "refine"}


# ------------------------------------------------------------------
# Storage
# ------------------------------------------------------------------
def _supabase_headers():
    key = config.STANDALONE_SUPABASE_SERVICE_ROLE_KEY
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=ignore-duplicates,return=minimal",
    }


def init_sqlite():
    conn = sqlite3.connect(config.STANDALONE_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS standalone_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            user_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source TEXT,
            model TEXT,
            metadata TEXT,
            dedupe_key TEXT UNIQUE
        )
        """
    )
    # Older builds of this table lacked these columns.
    existing = {r[1] for r in conn.execute("PRAGMA table_info(standalone_events)")}
    for col in ("source", "model", "dedupe_key"):
        if col not in existing:
            conn.execute(f"ALTER TABLE standalone_events ADD COLUMN {col} TEXT")
    conn.commit()
    conn.close()


init_sqlite()


def _dedupe_key(row):
    """Stable hash so re-importing the same CSV does not double-count."""
    raw = "|".join([
        row["provider"], row["user_id"], row["operation"],
        row["created_at"], row.get("model") or "",
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def normalize_row(payload):
    """Validate and canonicalise one incoming event. Raises ValueError."""
    provider = config.normalize_provider(payload.get("provider"))
    if provider not in config.PROVIDERS:
        raise ValueError(
            f"provider must be one of {config.PROVIDERS} (got {payload.get('provider')!r})"
        )

    operation = config.normalize_operation(payload.get("operation"))
    if operation not in VALID_OPERATIONS:
        raise ValueError(
            f"operation must map to generate or refine (got {payload.get('operation')!r})"
        )

    user_id = str(payload.get("user_id") or "").strip().lower()
    if not user_id:
        raise ValueError("user_id is required (use the designer's work email)")

    created_at = payload.get("created_at")
    if created_at:
        try:
            ts = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"created_at is not ISO-8601: {created_at!r}")
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = datetime.now(timezone.utc)

    row = {
        "provider": provider,
        "user_id": user_id,
        "operation": operation,
        "created_at": ts.isoformat(),
        "source": payload.get("source") or "manual",
        "model": payload.get("model"),
        "metadata": payload.get("metadata") or {},
    }
    row["dedupe_key"] = _dedupe_key(row)
    return row


def insert_rows(rows):
    """Insert canonical rows. Returns the number accepted."""
    if not rows:
        return 0

    if config.standalone_configured():
        payload = [{
            "provider": r["provider"],
            "user_id": r["user_id"],
            "operation": r["operation"],
            "created_at": r["created_at"],
            "source": r["source"],
            "model": r["model"],
            "metadata": r["metadata"],
        } for r in rows]
        resp = requests.post(
            f"{config.STANDALONE_SUPABASE_URL.rstrip('/')}/rest/v1/{config.STANDALONE_TABLE}",
            headers=_supabase_headers(),
            json=payload,
            timeout=30,
        )
        if resp.status_code not in (200, 201, 204):
            raise RuntimeError(
                f"Supabase insert failed ({resp.status_code}): {resp.text[:400]}"
            )
        return len(payload)

    # Render's filesystem is ephemeral, so a silent SQLite fallback there
    # would accept events and lose them on the next restart. Fail loudly.
    if os.environ.get("RENDER"):
        raise RuntimeError(
            "STANDALONE_SUPABASE_URL / _SERVICE_ROLE_KEY are not configured. "
            "Refusing the SQLite fallback on an ephemeral filesystem, since "
            "those events would be lost on restart."
        )

    conn = sqlite3.connect(config.STANDALONE_DB_PATH)
    accepted = 0
    try:
        for r in rows:
            cur = conn.execute(
                "INSERT OR IGNORE INTO standalone_events "
                "(provider, user_id, operation, created_at, source, model, metadata, dedupe_key) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (r["provider"], r["user_id"], r["operation"], r["created_at"],
                 r["source"], r["model"], json.dumps(r["metadata"]), r["dedupe_key"]),
            )
            accepted += cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return accepted


# ------------------------------------------------------------------
# Auth
# ------------------------------------------------------------------
def require_token():
    if not config.REFRESH_TOKEN:
        abort(503, description="REFRESH_TOKEN is not set; refusing to expose this endpoint")
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth.split(" ", 1)[1] != config.REFRESH_TOKEN:
        abort(401)



def require_viewer():
    """Gate every page that shows designer-level data.

    Fails closed. An unconfigured deployment refuses to serve rather than
    publishing names, emails and per-person activity to anyone with the URL.
    """
    if not config.viewer_auth_ready():
        abort(503, description=(
            "DASHBOARD_PASSWORD is not set. These dashboards show named "
            "designers and their work emails, so they will not be served "
            "unauthenticated. Set DASHBOARD_PASSWORD, or set "
            "ALLOW_PUBLIC_DASHBOARDS=1 to deliberately publish them."
        ))
    if config.ALLOW_PUBLIC_DASHBOARDS and not config.DASHBOARD_PASSWORD:
        return
    auth = request.authorization
    if (auth and auth.username == config.DASHBOARD_USER
            and secrets.compare_digest(auth.password or "", config.DASHBOARD_PASSWORD)):
        return
    resp = make_response(jsonify({"error": "authentication required"}), 401)
    resp.headers["WWW-Authenticate"] = 'Basic realm="Image Generator dashboards"'
    abort(resp)


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------
@app.post("/log-standalone")
def log_standalone():
    require_token()
    if not request.is_json:
        return jsonify({"error": "expected application/json"}), 400
    try:
        row = normalize_row(request.get_json())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    try:
        insert_rows([row])
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify({"status": "ok", "stored": 1}), 201


@app.post("/import-standalone")
def import_standalone():
    """Bulk import. Accepts a CSV upload (field name `file`) or a raw CSV body
    with columns: provider,user_id,operation[,created_at][,model][,source]."""
    require_token()

    if "file" in request.files:
        text = request.files["file"].read().decode("utf-8-sig")
    else:
        text = request.get_data(as_text=True)
    if not text.strip():
        return jsonify({"error": "no CSV content supplied"}), 400

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return jsonify({"error": "CSV has no header row"}), 400

    rows, errors = [], []
    for line_no, raw in enumerate(reader, start=2):
        clean = {(k or "").strip().lower(): (v or "").strip()
                 for k, v in raw.items() if k}
        try:
            rows.append(normalize_row(clean))
        except ValueError as exc:
            errors.append({"line": line_no, "error": str(exc)})
        if len(errors) >= 25:
            break

    if errors and not rows:
        return jsonify({"error": "no valid rows", "details": errors}), 400

    try:
        stored = insert_rows(rows)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502

    return jsonify({
        "status": "ok",
        "parsed": len(rows),
        "stored": stored,
        "rejected": len(errors),
        "details": errors[:25],
    }), 201


@app.post("/refresh")
def refresh():
    require_token()
    with _refresh_lock:
        dataset = _rebuild()
    return jsonify({
        "status": "ok",
        "meta": dataset["meta"],
        "generated_at": dataset["generated_at"],
        "data_hash": dataset["data_hash"],
    })


INDEX_CARDS = [
    ("overall", "Tool Usage",
     "Everything generated through the MCP tool, both models."),
    ("chatgpt", "ChatGPT Standalone",
     "ChatGPT used directly, outside the tool, vs. in-tool."),
    ("gemini", "Gemini Standalone",
     "Gemini used directly, outside the tool, vs. in-tool."),
]


@app.get("/")
def index():
    """Landing page. Without this, hitting the root just 404s."""
    require_viewer()
    # A fresh deploy has no generated files yet, so build before describing them.
    ensure_fresh()
    built = {
        v: os.path.exists(os.path.join(config.BASE_DIR, f"dashboard_{v}.html"))
        for v, _, _ in INDEX_CARDS
    }
    cards = ""
    for variant, title, blurb in INDEX_CARDS:
        if built[variant]:
            cards += (
                f'<a class="card" href="/dashboard/{variant}">'
                f"<h2>{title}</h2><p>{blurb}</p>"
                f'<span class="go">Open &rarr;</span></a>'
            )
        else:
            cards += (
                f'<div class="card is-missing"><h2>{title}</h2><p>{blurb}</p>'
                f'<span class="go">Not built yet</span></div>'
            )

    missing = [v for v, ok in built.items() if not ok]
    warning = (
        '<p class="warn">Some dashboards have not been generated yet. Run '
        "<code>python image_generation_dashboard_sync.py</code>, or "
        "<code>POST /refresh</code> with your bearer token.</p>"
        if missing else ""
    )

    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Image Generator Adoption</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
  :root {{ color-scheme: light; --plane:#f9f9f7; --tile:#fff; --ink:#0b0b0b;
    --ink-2:#52514e; --muted:#898781; --border:rgba(11,11,11,.10); --accent:#4a3aa7; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ color-scheme: dark; --plane:#0d0d0d; --tile:#202020; --ink:#fff;
      --ink-2:#c3c2b7; --muted:#898781; --border:rgba(255,255,255,.10); --accent:#9085e9; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--plane); color:var(--ink);
    font-family:"IBM Plex Sans",system-ui,sans-serif; padding:40px clamp(16px,5vw,56px); }}
  .wrap {{ max-width:1000px; margin:0 auto; }}
  .eyebrow {{ font-size:12px; font-weight:600; letter-spacing:.08em;
    text-transform:uppercase; color:var(--accent); margin:0 0 6px; }}
  h1 {{ font-size:clamp(24px,3.4vw,32px); margin:0 0 8px; }}
  .sub {{ color:var(--ink-2); margin:0 0 28px; max-width:62ch; font-size:14.5px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; }}
  .card {{ display:block; background:var(--tile); border:1px solid var(--border);
    border-radius:12px; padding:20px; text-decoration:none; color:inherit; }}
  a.card:hover {{ border-color:var(--accent); }}
  .card h2 {{ font-size:16px; margin:0 0 6px; }}
  .card p {{ font-size:13px; color:var(--ink-2); margin:0 0 14px; }}
  .go {{ font-size:12.5px; font-weight:600; color:var(--accent); }}
  .card.is-missing {{ opacity:.55; }} .card.is-missing .go {{ color:var(--muted); }}
  .warn {{ font-size:13px; color:var(--ink-2); background:var(--tile);
    border:1px dashed var(--border); border-radius:10px; padding:14px 16px; margin:18px 0 0; }}
  code {{ font-family:"IBM Plex Mono",monospace; font-size:12px;
    background:var(--plane); padding:1px 5px; border-radius:4px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; margin-top:10px; }}
  td {{ padding:7px 0; border-bottom:1px solid var(--border); color:var(--ink-2); }}
  td:first-child {{ font-family:"IBM Plex Mono",monospace; color:var(--ink);
    white-space:nowrap; padding-right:18px; }}
  h3 {{ font-size:13px; text-transform:uppercase; letter-spacing:.04em;
    color:var(--muted); margin:36px 0 0; }}
</style></head>
<body><div class="wrap">
  <p class="eyebrow">Adoption</p>
  <h1>Image Generator dashboards</h1>
  <p class="sub">Adoption tracking for the Image Generator MCP tool and for
    ChatGPT and Gemini used directly outside it.</p>
  <div class="grid">{cards}</div>
  {warning}
  <h3>Endpoints</h3>
  <table>
    <tr><td>GET /health</td><td>Configuration and connection status</td></tr>
    <tr><td>GET /dashboard_data.json</td><td>All computed metrics as JSON</td></tr>
    <tr><td>POST /refresh</td><td>Re-pull and rebuild (bearer token)</td></tr>
    <tr><td>POST /log-standalone</td><td>Log one direct usage event (bearer token)</td></tr>
    <tr><td>POST /import-standalone</td><td>Bulk CSV import (bearer token)</td></tr>
  </table>
</div></body></html>"""


# ------------------------------------------------------------------
# Auto-refresh
# ------------------------------------------------------------------
# The dashboards are static files, so something has to rebuild them. Serving a
# page checks how old the data is and re-pulls when it has aged past the TTL.
_refresh_lock = threading.Lock()
_state = {
    "built_at": None,      # monotonic clock, for age comparisons
    "generated_at": None,  # wall clock, shown to the reader
    "data_hash": None,
    "last_error": None,
}


def _rebuild():
    """Re-pull and rewrite. Caller must hold the lock."""
    _, dataset = sync.build_dataset(date.today())
    sync.write_dashboards(dataset)
    _state["built_at"] = time.monotonic()
    _state["generated_at"] = dataset["generated_at"]
    _state["data_hash"] = dataset["data_hash"]
    _state["last_error"] = None
    return dataset


def ensure_fresh(force=False):
    """Rebuild if the data has aged out, or on an explicit request.

    A failure here is never fatal: the previously built files stay on disk and
    keep being served, with the error surfaced through /api/status rather than
    replacing a working dashboard with a stack trace.
    """
    with _refresh_lock:
        now = time.monotonic()
        built = _state["built_at"]
        age = None if built is None else now - built

        if force:
            # Rate-limit forced rebuilds so a stuck button cannot flood Supabase.
            if age is not None and age < config.MIN_REBUILD_INTERVAL:
                return False
        elif age is not None and age < config.AUTO_REFRESH_SECONDS:
            return False

        try:
            _rebuild()
            return True
        except Exception as exc:  # network, auth, schema drift
            _state["last_error"] = str(exc)[:300]
            if _state["built_at"] is None:
                _state["built_at"] = now  # don't retry on every single request
            return False


def _truthy(value):
    return str(value or "").lower() in ("1", "true", "yes")


@app.get("/api/status")
def api_status():
    """Polled by every served dashboard. Also the manual button's endpoint."""
    require_viewer()
    ensure_fresh(force=_truthy(request.args.get("refresh")))
    return jsonify({
        "data_hash": _state["data_hash"],
        "generated_at": _state["generated_at"],
        "auto_refresh_seconds": config.AUTO_REFRESH_SECONDS,
        "error": _state["last_error"],
    })


@app.get("/dashboard/<variant>")
def serve_dashboard(variant):
    require_viewer()
    if variant not in config.VARIANTS:
        return jsonify({"error": f"unknown dashboard {variant!r}",
                        "available": config.VARIANTS}), 404
    ensure_fresh(force=_truthy(request.args.get("refresh")))
    filename = f"dashboard_{variant}.html"
    if not os.path.exists(os.path.join(config.BASE_DIR, filename)):
        return jsonify({"error": "could not build dashboards",
                        "detail": _state["last_error"]}), 503
    resp = make_response(send_from_directory(config.BASE_DIR, filename))
    # The file is rewritten in place, so it must never be cached as if static.
    resp.headers["Cache-Control"] = "no-store, must-revalidate"
    return resp


@app.get("/dashboard_data.json")
def serve_dashboard_json():
    require_viewer()
    ensure_fresh(force=_truthy(request.args.get("refresh")))
    if not os.path.exists(os.path.join(config.BASE_DIR, "dashboard_data.json")):
        return jsonify({"error": "could not build dashboards",
                        "detail": _state["last_error"]}), 503
    resp = make_response(send_from_directory(config.BASE_DIR, "dashboard_data.json"))
    resp.headers["Cache-Control"] = "no-store, must-revalidate"
    return resp


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "launch_date": config.LAUNCH_DATE.isoformat(),
        "tool_supabase_configured": config.tool_configured(),
        "standalone_supabase_configured": config.standalone_configured(),
        "standalone_table": config.STANDALONE_TABLE,
        "sqlite_fallback": not config.standalone_configured(),
        "refresh_token_set": bool(config.REFRESH_TOKEN),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
