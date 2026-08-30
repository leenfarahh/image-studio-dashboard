"""Central configuration for the Image Generator adoption dashboards.

Secrets are read from .env (gitignored) - never hardcode keys in source.
"""
import os
from datetime import date

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------------------------
# Data sources
# ------------------------------------------------------------------
# The MCP tool's own Supabase project (generation_events, images, profiles).
TOOL_SUPABASE_URL = os.environ.get("TOOL_SUPABASE_URL", "")
TOOL_SUPABASE_API_KEY = os.environ.get("TOOL_SUPABASE_API_KEY", "")

# Separate project holding direct/outside-the-tool ChatGPT + Gemini usage.
STANDALONE_SUPABASE_URL = os.environ.get("STANDALONE_SUPABASE_URL", "")
STANDALONE_SUPABASE_SERVICE_ROLE_KEY = os.environ.get("STANDALONE_SUPABASE_SERVICE_ROLE_KEY", "")

STANDALONE_TABLE = "standalone_usage_events"
EVENTS_TABLE = "generation_events"
IMAGES_TABLE = "images"
PROFILES_TABLE = "profiles"

# Local SQLite fallback, only used when the standalone project is unreachable.
STANDALONE_DB_PATH = os.environ.get(
    "STANDALONE_DB_PATH", os.path.join(BASE_DIR, "standalone_events.db")
)

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
# The dashboards name individual designers, list their work emails and show
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
# "openai"; the standalone schema uses "chatgpt". Both normalise to "chatgpt".
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

# The three dashboards. The URLs point at the published Claude artifacts so each
# dashboard can link to the other two; update them if you republish elsewhere.
NAV_ITEMS = [
    {"variant": "overall", "label": "Tool Usage",
     "url": "https://claude.ai/code/artifact/d48f20cd-43b3-4aca-9bdd-bc493b88cdd4"},
    {"variant": "chatgpt", "label": "ChatGPT Standalone",
     "url": "https://claude.ai/code/artifact/d392e652-2ff2-4838-aabc-917f9cf4c70e"},
    {"variant": "gemini", "label": "Gemini Standalone",
     "url": "https://claude.ai/code/artifact/ed81e812-5543-46a1-bdac-52320f1255e9"},
]

VARIANTS = ["overall", "chatgpt", "gemini"]


def normalize_provider(value):
    return PROVIDER_ALIASES.get(str(value or "").strip().lower())


def normalize_operation(value):
    return OPERATION_ALIASES.get(str(value or "").strip().lower())


def tool_configured():
    return bool(TOOL_SUPABASE_URL and TOOL_SUPABASE_API_KEY)


def standalone_configured():
    return bool(STANDALONE_SUPABASE_URL and STANDALONE_SUPABASE_SERVICE_ROLE_KEY)
