# Image Generator adoption dashboards

Three dashboards measuring adoption of the Image Generator MCP tool:

| Dashboard | File | Measures |
|---|---|---|
| Tool usage | `dashboard_overall.html` | All image generation through the MCP tool, both models |
| ChatGPT standalone | `dashboard_chatgpt.html` | ChatGPT used **directly**, outside the tool, vs. in-tool |
| Gemini standalone | `dashboard_gemini.html` | Gemini used **directly**, outside the tool, vs. in-tool |

## Rebuild

```bash
pip install -r requirements.txt
python image_generation_dashboard_sync.py
```

Live data only. A misconfigured run exits non-zero and writes nothing rather than
publishing numbers that are not real.

## Layout

| File | Role |
|---|---|
| `config.py` | Settings, secrets from `.env`, launch date, provider/operation vocabulary |
| `datasource.py` | Fetches from both Supabase projects |
| `metrics.py` | Aggregation: adoption, retention, reliability, substitution |
| `render.py` | CSS, SVG chart primitives, the three page templates |
| `image_generation_dashboard_sync.py` | CLI entry point |
| `app.py` | Flask service: ingestion, refresh, serving |
| `standalone_usage_schema.sql` | Schema for the standalone (direct-usage) project |

## Serving

```bash
python app.py     # http://127.0.0.1:8080
```

`/` is an index linking to all three dashboards. Individual pages are at
`/dashboard/overall`, `/dashboard/chatgpt` and `/dashboard/gemini`. The dev
server does not auto-reload, so restart it after changing **code** (data
refreshes on its own, see below).

### Auto-refresh

A served dashboard keeps itself current. There are three layers:

1. **On load.** If the data is older than `AUTO_REFRESH_SECONDS` (default 120),
   serving the page re-pulls from Supabase first. A rebuild takes about 3s,
   almost entirely database round-trips; loads inside the TTL are ~1ms.
2. **While open.** The page polls `/api/status` every `POLL_SECONDS`
   (default 30) and reloads **only if the figures actually changed**, compared
   by content hash rather than build time. A rebuild that finds nothing new
   will not interrupt someone mid-read.
3. **Manual.** A "Refresh now" button forces a re-read. Forced rebuilds are
   rate-limited to one per `MIN_REBUILD_INTERVAL` (default 10s).

The bar also shows data age, turning amber past 15 minutes and red if the
server cannot be reached.

If Supabase is unreachable, the last good build stays on disk and keeps being
served; the error surfaces through `/api/status` rather than replacing a
working dashboard with an error page.

The refresh bar only appears when `app.py` is serving the page. A published
artifact or a file opened from disk is a static snapshot with no server to ask,
so the bar stays hidden rather than offering a button that cannot work.

## Deploying to Render

The repo root must be **this** folder, the one holding `app.py`. Render clones
the repository and runs the build from its root, so if the source sits beside
the repo rather than inside it, the deploy will succeed and serve nothing.

`render.yaml` describes the service. Either commit it and use a Blueprint, or
create a Web Service manually with:

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 60`
- Health check path: `/health`

Set these in the Render dashboard, never in the repo:

| Variable | Notes |
|---|---|
| `TOOL_SUPABASE_URL` / `TOOL_SUPABASE_API_KEY` | The tool's project |
| `STANDALONE_SUPABASE_URL` / `..._SERVICE_ROLE_KEY` | Direct-usage project |
| `DASHBOARD_PASSWORD` | **Required.** Without it the app refuses to serve |
| `DASHBOARD_USER` | Defaults to `prezlab` |
| `REFRESH_TOKEN` | Guards the ingestion and refresh endpoints |
| `LAUNCH_DATE` | Must not post-date the first real event |

### Access control

The dashboards name individual designers and show their work emails and
per-person activity. Viewing is therefore gated by HTTP Basic auth and the gate
**fails closed**: with no `DASHBOARD_PASSWORD` set, every page returns 503
rather than publishing staff data to anyone holding the URL. `/health` stays
open so Render's health check works. To publish deliberately, set
`ALLOW_PUBLIC_DASHBOARDS=1`.

### Notes on the platform

- **Ephemeral filesystem.** Generated HTML is rebuilt on demand, so losing it on
  restart is harmless. The SQLite fallback is *not* harmless, so it is refused
  when `RENDER` is set: configure the standalone Supabase project instead.
- **Multiple workers.** Each gunicorn worker keeps its own refresh cache and
  rebuilds independently. Files are written to a temp path and renamed, so
  concurrent rebuilds cannot produce a half-written page.
- **Cold starts.** On a plan that spins down, the first request pays both the
  spin-up and a ~3s rebuild.
- **UTC.** Render runs in UTC, so generated timestamps display in UTC.

## The two data sources

**In-tool usage** comes from the tool's own Supabase project: `generation_events`
(including failures), `images` (for save rate and refine chains) and `profiles`
(the adoption denominator). This flows automatically.

**Direct usage** — ChatGPT or Gemini used outside the tool — has no automatic
feed. The vendor consoles do not push per-designer image counts anywhere, so it
must be supplied. Until it is, dashboards 2 and 3 show a zero direct channel and
say so on the page; that is a missing feed, not a measured zero.

### Feeding direct usage

Both endpoints need `Authorization: Bearer $REFRESH_TOKEN`.

Single event:

```bash
curl -X POST https://<host>/log-standalone \
  -H "Authorization: Bearer $REFRESH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider":"chatgpt","user_id":"designer@prezlab.com","operation":"generate"}'
```

Bulk, from an admin-console export:

```bash
curl -X POST https://<host>/import-standalone \
  -H "Authorization: Bearer $REFRESH_TOKEN" \
  -F file=@chatgpt_august.csv
```

CSV columns: `provider,user_id,operation[,created_at][,model][,source]`.

Rows carry a `dedupe_key`, so re-importing the same export does not double-count.
Invalid rows are rejected individually and reported back with line numbers; valid
rows in the same file still import.

`user_id` must be the designer's **work email**, lowercased. That is what joins
this data to `profiles` and lets the dashboards tell "uses ChatGPT directly but
never through the tool" apart from "has not started".

## No sample data, ever

These dashboards render live data or zero. There is no sample-data path and no
placeholder values. Specifically:

- No usage means every count and percentage reads `0`, not a dash or a blank.
- A zero-attempt success rate reads `0%` with a neutral "No attempts yet" badge.
  It does **not** read 100%, which would assert reliability off an empty sample.
- Latency with no samples reads `0.0s`.
- Last-used with no activity reads `Never`, since a date has no zero.
- Where a whole channel has no feed yet, the page says so in plain language
  rather than implying a measured zero.

Earlier fabricated sample dashboards were moved to `_archive/`. Do not publish
them.

## Metric definitions

- **Adoption rate** — distinct people who ever generated, over active rows in
  `profiles`. Because `profiles` fills in on first sign-in, this measures
  activation among provisioned designers, not reach across the whole team. To
  measure the latter, swap the denominator for a headcount constant.
- **Active users (weekly)** — distinct people in that week. Not the max of the
  daily counts, which undercounts any week where different people show up on
  different days.
- **Returning / repeat rate** — share of adopters active in 2+ distinct weeks.
  "Tried once" and "adopted" are not the same thing.
- **Save rate** — share of generated images with `saved = true`. The strongest
  available signal that a render was good enough to use.
- **Tool share** — in-tool actions over all actions for that model. The
  substitution metric: is image work running through the tool or around it?
- **Direct only** — people using a model directly who have never used it in the
  tool. The conversion list.

## Configuration

`.env` (gitignored):

```
TOOL_SUPABASE_URL=...
TOOL_SUPABASE_API_KEY=...
STANDALONE_SUPABASE_URL=...
STANDALONE_SUPABASE_SERVICE_ROLE_KEY=...
REFRESH_TOKEN=...
LAUNCH_DATE=2026-08-23     # must not post-date the first real event
PORT=8080
```

`LAUNCH_DATE` is applied as a `gte` filter on every fetch. Setting it later than
your first event silently drops history rather than erroring.

If the standalone project is unreachable, ingestion falls back to a local SQLite
file at `STANDALONE_DB_PATH`.

## Chart palette

The categorical hues, the funnel ramp and the status steps were validated with
the data-viz palette checker in both light and dark mode (lightness band, chroma
floor, CVD separation, normal-vision floor, contrast). Notably, violet fails
against the ChatGPT blue in dark mode, which is why the direct-usage channel is
teal. Re-run the validator before changing any of them.
