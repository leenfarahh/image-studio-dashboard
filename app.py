"""Refresh + serve layer for the adoption dashboard.

Endpoints
    POST /refresh            re-pull everything and rebuild the three views
    GET  /dashboard/<name>   serve a rendered view (overall, chatgpt, gemini)
    GET  /dashboard_data.json
    GET  /health

Read-only with respect to the data: every figure comes from the tool's own
Supabase project, so there is nothing to write and no ingestion to guard.
"""
import os
import secrets
import threading
import time
from datetime import date

from flask import Flask, abort, jsonify, make_response, request, send_from_directory

import assets
import config
import image_generation_dashboard_sync as sync

app = Flask(__name__)

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
    ("overall", "Overall",
     "Everything generated through the tool, both models combined."),
    ("chatgpt", "ChatGPT",
     "ChatGPT image generation in the tool: volume, reliability, save rate."),
    ("gemini", "Gemini",
     "Gemini image generation in the tool: volume, reliability, save rate."),
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
{assets.FAVICON_LINK}
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700;800&display=swap">
<style>
  :root {{ color-scheme: light; --plane:#f5efe8; --tile:#fffefd; --ink:#002528;
    --ink-2:#425a5d; --muted:#728486; --border:rgba(0,37,40,.12); --accent:#002528;
    --rule:#b6edf3; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ color-scheme: dark; --plane:#0a1c1e; --tile:#173235; --ink:#eef8f9;
      --ink-2:#acc3c5; --muted:#839698; --border:rgba(182,237,243,.14);
      --accent:#b6edf3; --rule:#00939f; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--plane); color:var(--ink);
    font-family:"Figtree",system-ui,-apple-system,"Segoe UI",sans-serif; padding:40px clamp(16px,5vw,56px); }}
  .wrap {{ max-width:1000px; margin:0 auto; }}
  .eyebrow {{ font-size:12px; font-weight:600; letter-spacing:.08em;
    text-transform:uppercase; color:var(--accent); margin:0 0 6px; }}
  h1 {{ font-family:"PP Editorial New",Georgia,"Iowan Old Style",serif;
    font-weight:400; font-size:clamp(28px,4vw,40px); letter-spacing:-.01em;
    margin:0 0 8px; }}
  .sub {{ color:var(--ink-2); margin:0 0 28px; max-width:62ch; font-size:14.5px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; }}
  .card {{ display:block; background:var(--tile); border:1px solid var(--border);
    border-radius:12px; padding:20px; text-decoration:none; color:inherit; }}
  a.card:hover {{ border-color:var(--accent); box-shadow:inset 3px 0 0 var(--rule); }}
  .card h2 {{ font-size:16px; margin:0 0 6px; }}
  .card p {{ font-size:13px; color:var(--ink-2); margin:0 0 14px; }}
  .go {{ font-size:12.5px; font-weight:600; color:var(--accent); }}
  .card.is-missing {{ opacity:.55; }} .card.is-missing .go {{ color:var(--muted); }}
  .warn {{ font-size:13px; color:var(--ink-2); background:var(--tile);
    border:1px dashed var(--border); border-radius:10px; padding:14px 16px; margin:18px 0 0; }}
  code {{ font-family:"Figtree",ui-monospace,monospace; font-variant-numeric:tabular-nums; font-size:12px;
    background:var(--plane); padding:1px 5px; border-radius:4px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; margin-top:10px; }}
  td {{ padding:7px 0; border-bottom:1px solid var(--border); color:var(--ink-2); }}
  td:first-child {{ font-family:"Figtree",ui-monospace,monospace; font-variant-numeric:tabular-nums; color:var(--ink);
    white-space:nowrap; padding-right:18px; }}
  h3 {{ font-size:13px; text-transform:uppercase; letter-spacing:.04em;
    color:var(--muted); margin:36px 0 0; padding-top:14px;
    border-top:2px solid var(--rule); }}
</style></head>
<body><div class="wrap">
  <p class="eyebrow">Adoption</p>
  <h1>Image Generator adoption</h1>
  <p class="sub">Every image generated through the Image Generator MCP tool,
    measured against the designers provisioned on it. Both models together,
    then each on its own.</p>
  <div class="grid">{cards}</div>
  {warning}
  <h3>Endpoints</h3>
  <table>
    <tr><td>GET /health</td><td>Configuration and connection status</td></tr>
    <tr><td>GET /dashboard_data.json</td><td>All computed metrics as JSON</td></tr>
    <tr><td>POST /refresh</td><td>Re-pull and rebuild (bearer token)</td></tr>
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


@app.get("/favicon.ico")
def favicon():
    """Served unauthenticated, like /health.

    Pages carry the mark inline so nothing normally requests this, but a
    browser will ask for it unprompted on a bare URL, and a company logo is
    not the staff data the viewer gate exists to protect.
    """
    if not os.path.exists(assets.LOGO_PATH):
        return "", 404
    resp = make_response(send_from_directory(config.BASE_DIR, assets.LOGO_FILE))
    resp.headers["Content-Type"] = assets.LOGO_MIME
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "launch_date": config.LAUNCH_DATE.isoformat(),
        "tool_supabase_configured": config.tool_configured(),
        "refresh_token_set": bool(config.REFRESH_TOKEN),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
