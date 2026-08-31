"""Brand assets, inlined at import.

The same generated HTML is served by app.py, opened straight off disk, and
published as an artifact. A favicon referenced by path only resolves in the
first of those, so the mark travels with the file as a data URI instead.

At 3KB the logo costs less inlined than a second round trip would, and there
is no separate file for a deploy to forget to copy.
"""
import base64
import os

import config

LOGO_FILE = "logo_short.jpg"
LOGO_PATH = os.path.join(config.BASE_DIR, LOGO_FILE)
LOGO_MIME = "image/jpeg"


def _data_uri():
    """A missing logo is cosmetic, not a reason to stop serving the numbers.

    Every caller treats an empty string as "no favicon" and the browser falls
    back to its own default mark.
    """
    try:
        with open(LOGO_PATH, "rb") as fh:
            encoded = base64.b64encode(fh.read()).decode("ascii")
    except OSError:
        return ""
    return f"data:{LOGO_MIME};base64,{encoded}"


LOGO_DATA_URI = _data_uri()

FAVICON_LINK = (
    f'<link rel="icon" type="{LOGO_MIME}" href="{LOGO_DATA_URI}">'
    if LOGO_DATA_URI else ""
)
