# Image Generator adoption dashboard

One dashboard measuring adoption of the Image Generator MCP tool, in three views:

| View | File | Measures |
|---|---|---|
| Overall | `dashboard_overall.html` | Everything generated through the tool, both models combined |
| ChatGPT | `dashboard_chatgpt.html` | ChatGPT image generation in the tool |
| Gemini | `dashboard_gemini.html` | Gemini image generation in the tool |

Every figure describes work that ran **through the tool**. Usage outside it is
deliberately not tracked: no vendor exposes per-designer image counts, so any
such number would be self-reported or inferred. See [Why in-tool only](#why-in-tool-only).

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
| `datasource.py` | Fetches from the tool's Supabase project |
| `metrics.py` | Aggregation: adoption, retention, reliability, model mix |
| `render.py` | CSS, SVG chart primitives, the page templates |
| `image_generation_dashboard_sync.py` | CLI entry point |
| `app.py` | Flask service: refresh and serving |

## Serving

```bash
python app.py     # http://127.0.0.1:8080
```

`/` is an index linking to all three views, which live at `/dashboard/overall`,
`/dashboard/chatgpt` and `/dashboard/gemini`. The dev server does not
auto-reload, so restart it after changing **code** (data refreshes on its own,
see below).

### Auto-refresh

A served view keeps itself current. There are three layers:

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
working page with an error page.

The refresh bar only appears when `app.py` is serving the page. A file opened
straight off disk is a static snapshot with no server to ask, so the bar stays
hidden rather than offering a button that cannot work.

## Deploying to Render

The repo root must be **this** folder, the one holding `app.py`. Render clones
the repository and runs the build from its root, so if the source sits beside
the repo rather than inside it, the deploy will succeed and serve nothing.

`render.yaml` describes the service. Either commit it and use a Blueprint, or
create a Web Service manually with:

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 60`
- Health check path: `/health` (under **Advanced** on the manual form)

Set these in the Render dashboard, never in the repo:

| Variable | Notes |
|---|---|
| `TOOL_SUPABASE_URL` / `TOOL_SUPABASE_API_KEY` | The tool's project, the only data source |
| `DASHBOARD_PASSWORD` | **Required.** Without it the app refuses to serve |
| `DASHBOARD_USER` | Defaults to `prezlab` |
| `REFRESH_TOKEN` | Guards `POST /refresh` |
| `LAUNCH_DATE` | Must not post-date the first real event |
| `PYTHON_VERSION` | **Required.** Render ignores `runtime.txt` and otherwise picks its own default |

Do **not** set `PORT`. Render assigns one and injects it; overriding it makes
gunicorn bind a port the health check is not probing.

### Access control

The views name individual designers and show their work emails and per-person
activity. Viewing is therefore gated by HTTP Basic auth and the gate **fails
closed**: with no `DASHBOARD_PASSWORD` set, every page returns 503 rather than
publishing staff data to anyone holding the URL. `/health` stays open so
Render's health check works. To publish deliberately, set
`ALLOW_PUBLIC_DASHBOARDS=1`.

### Notes on the platform

- **Ephemeral filesystem.** Generated HTML is rebuilt on demand, so losing it on
  restart is harmless. Nothing is written that needs to survive a restart.
- **Multiple workers.** Each gunicorn worker keeps its own refresh cache and
  rebuilds independently. Files are written to a temp path and renamed, so
  concurrent rebuilds cannot produce a half-written page.
- **Cold starts.** On a plan that spins down, the first request pays both the
  spin-up and a ~3s rebuild.
- **UTC.** Render runs in UTC, so generated timestamps display in UTC.

## The data source

Everything comes from the tool's own Supabase project:

- `generation_events` — every attempt, **including failures**. Reliability is an
  adoption driver, and filtering on `success = true` makes every error invisible.
- `images` — save rate and refine chains.
- `profiles` — the adoption denominator.

This flows automatically. There is nothing to feed in and no ingestion endpoint.

### Why in-tool only

An earlier version tracked ChatGPT and Gemini used *outside* the tool, fed by a
second Supabase project and two ingestion endpoints. That channel is gone.

Nothing reports it. OpenAI's Admin and Cost APIs cover API platform traffic, not
what someone does on chatgpt.com, and per-user Gemini reporting requires Google
Workspace. Without a vendor workspace the only feeds available are self-reporting
or network-level monitoring, and neither yields a per-image count.

A channel that is always zero is worse than no channel: it reads as a measured
finding when it is a missing feed. If a ChatGPT Business or Enterprise workspace
is provisioned later, the workspace analytics export is the path to revisit.

## No sample data, ever

These views render live data or zero. There is no sample-data path and no
placeholder values. Specifically:

- No usage means every count and percentage reads `0`, not a dash or a blank.
- A zero-attempt success rate reads `0%` with a neutral "No attempts yet" badge.
  It does **not** read 100%, which would assert reliability off an empty sample.
- Latency with no samples reads `0.0s`.
- Last-used with no activity reads `Never`, since a date has no zero.
- A provider view with no activity says so in plain language, and says
  explicitly that the zero is measured rather than missing.

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
- **Share of volume** — one model's successful actions over all successful
  in-tool actions. Which model the work actually runs on.
- **Refines per generate** — reworks divided by first-pass generations. A high
  ratio means that model takes more iterations before anyone keeps the result.
- **Model only / both** — designers who have settled on one model versus those
  who reach for either.

## Configuration

`.env` (gitignored):

```
TOOL_SUPABASE_URL=...
TOOL_SUPABASE_API_KEY=...
REFRESH_TOKEN=...
DASHBOARD_USER=prezlab
DASHBOARD_PASSWORD=...
LAUNCH_DATE=2026-08-23     # must not post-date the first real event
PORT=8080                  # local dev only, never set this on Render
```

`LAUNCH_DATE` is applied as a `gte` filter on every fetch. Setting it later than
your first event silently drops history rather than erroring.

## Brand palette

| Token | Value | Use |
|---|---|---|
| Dark Teal | `#002528` | Primary. `--ink` and `--accent` in light mode, the dark surface in dark mode |
| Light Teal | `#b6edf3` | Accent. Rules, the active nav pill, `--accent` in dark mode |
| Sand | `#e3d8cc` | Warm neutral. `--sand` for callout panels; the page plane is a lighter tint of it |
| Figtree | sans | Body and UI, loaded from Google Fonts |
| PP Editorial New | serif display | `.dash-title` and the landing `h1` |

**PP Editorial New has no webfont here.** It is a licensed Pangram Pangram face,
not on Google Fonts, so it leads the display stack and falls back to Georgia for
anyone without it installed. To render it for everyone, self-host the licensed
files and add an `@font-face`.

### Chart colors are derived, not brand tokens

None of the three brand colors can be a chart series color. Measured in OKLCH:

```
Dark Teal   #002528  L=0.241  C=0.041   lightness band FAIL, chroma FAIL
Light Teal  #b6edf3  L=0.910  C=0.056   lightness band FAIL, chroma FAIL
Sand        #e3d8cc  L=0.888  C=0.020   lightness band FAIL, chroma FAIL
```

Two are near-white and one is near-black, and all three sit under the 0.10 chroma
floor where a hue stops carrying identity. So the categorical pair is **derived on
the brand hue axes**: teal at H=203 (the hue both brand teals share) and a clay at
H=45 (the warm family Sand belongs to), each stepped to a passing lightness.

| Slot | Light | Dark |
|---|---|---|
| `--chatgpt` | `#00939f` | `#00a1ac` |
| `--gemini` | `#c65d26` | `#cd632d` |
| funnel ramp | `#6ac1c9 #34a4ad #008994 #00616a` | `#7ccdd5 #40b1ba #00939f #006d76` |

Validated against the six checks in both modes: lightness band, chroma floor,
CVD separation under Machado-Oliveira-Fernandes 2009 at severity 1.0, the
normal-vision floor, and contrast. The categorical pair clears CVD at 16.6 light
and 16.6 dark against a target of 8, and the normal-vision floor at 24.9 and 25.7
against a floor of 15.

Two-series charts that show **one** quantity (generate vs refine, active vs
cumulative) use two steps of a single hue rather than a second categorical slot.
They are a composition and an aggregation, not two identities, so they take the
ordinal rule: monotone lightness, adjacent delta L >= 0.06, light end >= 2:1 on
surface. Re-validate before changing any of these.

Status colors (`--good` `--warning` `--critical`) are deliberately **not**
brand-mapped. Red, amber and green carry meaning that overrides brand fit, and
they always ship with an icon and a label rather than color alone.
