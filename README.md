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
cp .env.example .env      # then fill in the Supabase keys and a dashboard password
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
| `assets.py` | The brand mark, inlined as a data URI for the favicon |
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

A served view keeps itself current with no interaction. There are two layers:

1. **On load.** If the data is older than `AUTO_REFRESH_SECONDS` (default 120),
   serving the page re-pulls from Supabase first. A rebuild takes about 3s,
   almost entirely database round-trips; loads inside the TTL are ~1ms.
2. **While open.** The page polls `/api/status` every `POLL_SECONDS`
   (default 30) and reloads **only if the figures actually changed**, compared
   by content hash rather than build time. A rebuild that finds nothing new
   will not interrupt someone mid-read. It also re-checks whenever you switch
   back to the tab.

Worst case, a change in Supabase reaches an open page in
`AUTO_REFRESH_SECONDS + POLL_SECONDS`, about 150 seconds on the defaults.

**There is no refresh button, deliberately.** A browser reload is not a force:
it goes through the same 120s cache and serves the cached build inside it. So
the only thing a button did was read through that cache a couple of minutes
early, on a dashboard measuring a rollout over weeks. Appending `?refresh=1` to
`/api/status`, `/dashboard/<name>` or `/dashboard_data.json` still forces a
read, rate-limited to one per `MIN_REBUILD_INTERVAL` (default 10s), for when
you do need one from the URL.

The bar shows data age, turning amber past 15 minutes and red if the server
cannot be reached.

If Supabase is unreachable, the last good build stays on disk and keeps being
served; the error surfaces through `/api/status` rather than replacing a
working page with an error page.

The bar only appears when `app.py` is serving the page. A file opened straight
off disk is a static snapshot with no server to ask, so the bar stays hidden
rather than reporting an age it cannot keep current.

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

## Weekly or daily

Every view carries a **Measured by** switch: `Weekly` or `Daily`. It changes the
bucket that people-based metrics are counted in, and so changes what "came back"
means:

| Element | Weekly | Daily |
|---|---|---|
| Returning users KPI | active in 2+ calendar weeks | active on 2+ distinct days |
| Adoption funnel | "Came back a 2nd week" | "Came back a 2nd day" |
| Stickiness panel | returning, avg active weeks | returning, avg active days |
| Volume and adopter charts | one point per week | one point per day |
| By-designer table | Active weeks, and status | Active days, and status |

Both readings are true and neither replaces the other. A second week is the
stricter test of a habit, but in the first week of a rollout **nobody can have
passed it yet**, so a weekly-only dashboard reports 0% returning while designers
are visibly coming back the next day. The daily read surfaces that signal early;
the weekly read is the one to judge a habit by once there is enough history.

Everything not counted in periods is identical across the two: adoption rate,
total actions, success rate, save rate, latency and the model split are the same
numbers either way, and deliberately do not move when the switch does.

Mechanically, both granularities are rendered into the page and the switch only
flips which is visible, so it needs no server round trip and works on a file
opened straight off disk. The choice is remembered in `localStorage`, because a
page that reloads itself on new data would otherwise snap a daily reader back to
weekly mid-read.

## Retries, and what "a generation" counts

The MCP client gives up on a slow generation and calls the tool again. The
server has usually finished by then, so it writes an event row and stores an
image that never reached the designer. One picture, three rows, three library
images. Left alone, those retries read as extra successful generations and
inflate volume, share of model, and median latency all at once.

An attempt is treated as **superseded** when the same person re-renders an
identical prompt on the same model within `RETRY_WINDOW_SECONDS` (default 300)
**and** that attempt ran at or past `CLIENT_TIMEOUT_MS` (default 75000). Both
conditions are required. A designer re-running a prompt they did not like is a
real second generation, and the timeout is the only thing separating that from
a client retry. Detection needs the prompt, so an attempt with no matching
image row stays counted as delivered: this under-reports rather than inventing
retries out of missing data.

Every row therefore carries two flags:

| Flag | Meaning |
|---|---|
| `delivered` | Succeeded **and** reached the designer. This is what "a generation" means in every count on the dashboard. |
| `superseded` | Completed server-side, then a retry replaced it. A failure from where the designer sits, even though the tool recorded a success. |

Both are reported side by side in the health panel, never summed into one
"failures" number, because they are known to very different standards.

### The tool does not log its failures

`generation_events` gets a row only **after** a generation succeeds. There is no
insert on the failure path, so `success` has never once been `false` and
`error_code` has never been populated. A hard API error leaves no trace at all.

This is why the dashboard can show a 0 next to "Failures logged by the tool"
on the same day a designer watched two attempts error out. That zero is a
missing feed, not a clean record, and the panel says so in those words rather
than letting it read as reliability. Superseded attempts can be reported only
because the rows they left behind do exist.

**Fixing this properly is a change to the MCP tool, not to this repo.** The
tool should write an event row on the failure path too, with `success = false`
and a real `error_code`. Until it does, "Failures logged by the tool" is a
floor, and the true delivered rate is at or below what is shown here.

## Metric definitions

- **Adoption rate** — distinct people who ever generated, over active rows in
  `profiles`. Because `profiles` fills in on first sign-in, this measures
  activation among provisioned designers, not reach across the whole team. To
  measure the latter, swap the denominator for a headcount constant.
- **Active users (per period)** — distinct people in that bucket. A week is
  not the max of its daily counts, which would undercount any week where
  different people show up on different days; it is a fresh distinct count.
- **Returning / repeat rate** — share of adopters active in 2+ distinct
  periods, weeks or days depending on the switch. "Tried once" and "adopted" are
  not the same thing. `retention` in `dashboard_data.json` is keyed by period.
- **Delivered rate** — attempts that succeeded and reached the designer, over
  all attempts. Replaces the old success rate, which divided the rows the tool
  wrote by the rows the tool wrote and so could only ever be 100%.
- **Save rate** — share of delivered images with `saved = true`. The strongest
  available signal that a render was good enough to use. Superseded renders are
  excluded from the denominator: nobody declined to keep an image they never
  saw.
- **Share of volume** — one model's delivered actions over all delivered
  in-tool actions. Which model the work actually runs on.
- **Refines per generate** — reworks divided by first-pass generations. A high
  ratio means that model takes more iterations before anyone keeps the result.
- **Model only / both** — designers who have settled on one model versus those
  who reach for either.

## Configuration

Copy `.env.example` to `.env` (gitignored) and fill it in. Every variable is
documented there; the ones that matter:

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

### The mark

`logo_short.jpg` is the favicon, inlined as a `data:` URI by `assets.py` rather
than linked by path. The same generated HTML is served by `app.py`, opened
straight off disk and published as an artifact, and a path only resolves in the
first of those. At 3KB it costs less inlined than a second round trip, and there
is no separate file for a deploy to forget. `app.py` also serves it at
`/favicon.ico`, unauthenticated like `/health`, for browsers that ask unprompted.
A missing logo file degrades to no favicon rather than breaking a build.

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
