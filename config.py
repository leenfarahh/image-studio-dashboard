"""Central configuration for the Image Generator adoption dashboard.

Secrets are read from .env (gitignored) - never hardcode keys in source.
"""
import os
from datetime import date

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------------------------
# Data source
# ------------------------------------------------------------------
# The MCP tool's own Supabase project, and the only source of truth. Usage
# outside the tool is deliberately not tracked: no vendor exposes per-designer
# image counts, so any such figure would be self-reported or inferred.
TOOL_SUPABASE_URL = os.environ.get("TOOL_SUPABASE_URL", "")
TOOL_SUPABASE_API_KEY = os.environ.get("TOOL_SUPABASE_API_KEY", "")

EVENTS_TABLE = "generation_events"
IMAGES_TABLE = "images"
PROFILES_TABLE = "profiles"

# ------------------------------------------------------------------
# Odoo (HR) - the adoption denominator
# ------------------------------------------------------------------
# Without this the denominator is "people provisioned on the tool", which
# flatters the number: anyone never provisioned cannot count as a non-adopter.
# Odoo answers the question the dashboard actually asks - how many designers
# are there - so headcount from HR is preferred and profiles are the fallback.
#
# Stock Odoo has no REST API. The external API is XML-RPC, authenticating with
# database + login + API key (Settings > My Profile > Account Security > New
# API Key). All four values are required for the lookup to run.
ODOO_URL = os.environ.get("ODOO_URL", "").rstrip("/")  # e.g. https://prezlab.odoo.com
ODOO_DB = os.environ.get("ODOO_DB", "")                # database name
ODOO_USERNAME = os.environ.get("ODOO_USERNAME", "")    # login email of the API user
ODOO_API_KEY = os.environ.get("ODOO_API_KEY", "")      # API key, used as the password
ODOO_DEPARTMENT = os.environ.get("ODOO_DEPARTMENT", "Creative")

# Sub-departments count toward the parent by default: "Creative" should include
# "Creative / Presentation Design" rather than only people filed at the top
# level. Set ODOO_INCLUDE_SUB_DEPARTMENTS=0 for an exact-department count.
ODOO_INCLUDE_SUB_DEPARTMENTS = os.environ.get("ODOO_INCLUDE_SUB_DEPARTMENTS", "1") != "0"

# Escape hatch for a deployment that has a REST layer installed on top of Odoo
# (OCA base_rest or similar). When set, this is tried instead of XML-RPC.
ODOO_API_URL = os.environ.get("ODOO_API_URL", "")


def odoo_configured():
    """True when every value the XML-RPC lookup needs is present."""
    return bool(ODOO_URL and ODOO_DB and ODOO_USERNAME and ODOO_API_KEY)


def odoo_rest_configured():
    return bool(ODOO_API_URL and ODOO_API_KEY)

REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN", "")

# ------------------------------------------------------------------
# Refresh behaviour
# ------------------------------------------------------------------
# A served dashboard rebuilds itself when its data is older than this. The
# rebuild costs ~3s, almost entirely Supabase round-trips, so this trades
# staleness against load on the database.
AUTO_REFRESH_SECONDS = int(os.environ.get("AUTO_REFRESH_SECONDS", "120"))

# Floor between forced rebuilds, so holding down the refresh button cannot
# turn into a stream of queries.
MIN_REBUILD_INTERVAL = int(os.environ.get("MIN_REBUILD_INTERVAL", "10"))

# How often a served page asks the server whether the numbers changed. The
# page only reloads when they actually differ, so this can be frequent.
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "30"))

# ------------------------------------------------------------------
# Viewer access
# ------------------------------------------------------------------
# The dashboard names individual designers, lists their work emails and shows
# per-person activity. On a public URL that is an internal data leak, so
# viewing is gated by default and the gate fails closed: with no password set
# the app refuses to serve rather than quietly publishing staff data.
# Set ALLOW_PUBLIC_DASHBOARDS=1 only for a deliberately public deployment.
DASHBOARD_USER = os.environ.get("DASHBOARD_USER", "prezlab")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")
ALLOW_PUBLIC_DASHBOARDS = os.environ.get("ALLOW_PUBLIC_DASHBOARDS", "") == "1"


def viewer_auth_ready():
    """True when it is safe to serve: either gated, or explicitly opted out."""
    return bool(DASHBOARD_PASSWORD) or ALLOW_PUBLIC_DASHBOARDS

# ------------------------------------------------------------------
# Reporting window
# ------------------------------------------------------------------
# First day of activity to report on. This must not be later than the first
# real event or the gte filter silently drops history.
LAUNCH_DATE = date.fromisoformat(os.environ.get("LAUNCH_DATE", "2026-08-23"))

# ------------------------------------------------------------------
# Vocabulary
# ------------------------------------------------------------------
# Canonical provider keys used everywhere downstream. The tool logs OpenAI as
# "openai"; both spellings normalise to "chatgpt".
PROVIDERS = ["chatgpt", "gemini"]

PROVIDER_ALIASES = {
    "openai": "chatgpt",
    "chatgpt": "chatgpt",
    "gpt": "chatgpt",
    "gemini": "gemini",
    "google": "gemini",
}

# Canonical operations. Anything that reworks an existing image is a "refine".
OPERATION_ALIASES = {
    "generate": "generate",
    "create": "generate",
    "edit": "refine",
    "refine": "refine",
    "variation": "refine",
    "upscale": "refine",
}

PROVIDER_LABELS = {"chatgpt": "ChatGPT", "gemini": "Gemini"}

# ------------------------------------------------------------------
# Reporting period
# ------------------------------------------------------------------
# Every people-based metric buckets activity into periods, and "returning"
# means active in 2+ of them. Which period is the honest one depends on how
# young the rollout is: in week one nobody can have a second week yet, so a
# weekly-only read prints 0% returning even while designers are coming back
# day after day. Both granularities are computed and the reader picks.
PERIODS = ["week", "day"]
DEFAULT_PERIOD = "week"
PERIOD_LABELS = {"week": "Weekly", "day": "Daily"}
PERIOD_NOUN = {"week": "week", "day": "day"}
PERIOD_NOUN_PLURAL = {"week": "weeks", "day": "days"}

# ------------------------------------------------------------------
# Retry detection
# ------------------------------------------------------------------
# The MCP client gives up on a slow generation and calls the tool again. The
# server has usually finished by then, so it writes an event row and stores an
# image that never reached the designer. Left alone, those land in the data as
# extra successful generations: three rows and three library images for one
# picture the designer actually received.
#
# An attempt is treated as superseded when the same person re-renders an
# identical prompt on the same model within RETRY_WINDOW_SECONDS *and* that
# attempt ran at or past CLIENT_TIMEOUT_MS. Both conditions are required. A
# designer re-running a prompt they did not like is a real second generation,
# and the timeout is the only thing separating that from a client retry.
#
# The defaults were set against observed data, where every superseded attempt
# ran 81s or longer and every delivered one finished inside 55s. Raise
# CLIENT_TIMEOUT_MS if the tool's own timeout is raised.
RETRY_WINDOW_SECONDS = int(os.environ.get("RETRY_WINDOW_SECONDS", "300"))
CLIENT_TIMEOUT_MS = int(os.environ.get("CLIENT_TIMEOUT_MS", "75000"))

# One dashboard, three views: both models together, then each on its own.
# No absolute URLs, so _nav falls back to the served path and NAV_JS rewrites
# it for a page opened straight off disk.
NAV_ITEMS = [
    {"variant": "overall", "label": "Overall"},
    {"variant": "chatgpt", "label": "ChatGPT"},
    {"variant": "gemini", "label": "Gemini"},
]

VARIANTS = ["overall", "chatgpt", "gemini"]


def normalize_provider(value):
    return PROVIDER_ALIASES.get(str(value or "").strip().lower())


def normalize_operation(value):
    return OPERATION_ALIASES.get(str(value or "").strip().lower())


def tool_configured():
    return bool(TOOL_SUPABASE_URL and TOOL_SUPABASE_API_KEY)
