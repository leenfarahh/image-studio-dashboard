"""Fetch layer: pulls raw rows from the tool's Supabase project."""
import xmlrpc.client
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


class OdooError(RuntimeError):
    """Odoo was configured but the headcount lookup failed.

    Distinct from "not configured" (which returns None) so a broken credential
    is never mistaken for a deliberate opt-out.
    """


def _odoo_models():
    """Authenticate over XML-RPC and return (uid, models_proxy).

    Every failure mode here raises OdooError with the step that failed, since
    "wrong database" and "wrong API key" are otherwise indistinguishable.
    """
    common = xmlrpc.client.ServerProxy(
        f"{config.ODOO_URL}/xmlrpc/2/common", allow_none=True
    )
    try:
        common.version()
    except Exception as exc:
        raise OdooError(f"cannot reach {config.ODOO_URL}/xmlrpc/2/common: {exc}") from exc

    try:
        uid = common.authenticate(
            config.ODOO_DB, config.ODOO_USERNAME, config.ODOO_API_KEY, {}
        )
    except xmlrpc.client.Fault as exc:
        # A wrong database name comes back as a Fault, not a falsy uid.
        raise OdooError(f"authenticate failed (check ODOO_DB): {exc.faultString}") from exc

    if not uid:
        raise OdooError(
            f"authenticate returned no uid for {config.ODOO_USERNAME} on "
            f"database {config.ODOO_DB!r} - check the login and API key"
        )

    models = xmlrpc.client.ServerProxy(
        f"{config.ODOO_URL}/xmlrpc/2/object", allow_none=True
    )
    return uid, models


def _execute(models, uid, model, method, *args, **kwargs):
    try:
        return models.execute_kw(
            config.ODOO_DB, uid, config.ODOO_API_KEY, model, method, list(args), kwargs
        )
    except xmlrpc.client.Fault as exc:
        raise OdooError(f"{model}.{method} failed: {exc.faultString.strip()}") from exc


def _department_ids(models, uid):
    """Resolve the configured department name to ids, sub-departments included.

    Matched case-insensitively on the exact name: an `ilike` substring match
    would fold "Creative Ops" into "Creative" and quietly inflate headcount.
    """
    ids = _execute(
        models, uid, "hr.department", "search",
        [("name", "=ilike", config.ODOO_DEPARTMENT)],
    )
    if not ids:
        known = _execute(models, uid, "hr.department", "search_read", [],
                         fields=["name"], limit=50)
        names = ", ".join(sorted(d["name"] for d in known)) or "none visible"
        raise OdooError(
            f"no department named {config.ODOO_DEPARTMENT!r}. Departments: {names}"
        )
    if not config.ODOO_INCLUDE_SUB_DEPARTMENTS:
        return ids
    return _execute(
        models, uid, "hr.department", "search", [("id", "child_of", ids)]
    )


def fetch_department_roster():
    """Who is in the configured department, from Odoo HR.

    Returns {"count": int, "emails": [work emails]}, or None when Odoo is not
    configured at all. Raises OdooError when it is configured and the lookup
    fails - a silent None there would swap in the provisioned-profile count and
    overstate adoption without saying so.

    The emails matter as much as the count. A headcount alone gives a
    denominator but no way to tell whether the people in the numerator belong
    to it, and the tool is provisioned well outside this department.

    Archived employees are excluded: Odoo applies its own active filter unless
    told otherwise, which is what we want here - leavers are not designers who
    failed to adopt.
    """
    if config.odoo_rest_configured():
        return {"count": _fetch_headcount_rest(), "emails": []}
    if not config.odoo_configured():
        return None

    uid, models = _odoo_models()
    dept_ids = _department_ids(models, uid)
    domain = [("department_id", "in", dept_ids)]

    for model in ("hr.employee", "hr.employee.public"):
        try:
            rows = _execute(models, uid, model, "search_read", domain,
                            fields=["work_email"], limit=2000)
        except OdooError:
            # An API user without HR rights cannot read hr.employee. The public
            # model carries the same rows with fewer fields and is enough here.
            if model == "hr.employee.public":
                raise
            continue
        emails = sorted({
            (r.get("work_email") or "").strip().lower()
            for r in rows if r.get("work_email")
        })
        return {"count": len(rows), "emails": emails}


def _fetch_headcount_rest():
    """Deployments with a REST layer bolted on top of Odoo.

    Kept because it was the original implementation; stock Odoo does not serve
    this and ODOO_API_URL should be left unset there.
    """
    url = config.ODOO_API_URL.rstrip("/") + "/employees"
    headers = {"Authorization": f"Bearer {config.ODOO_API_KEY}"}
    params = {"department": config.ODOO_DEPARTMENT}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
    except requests.RequestException as exc:
        raise OdooError(f"cannot reach {url}: {exc}") from exc
    if resp.status_code != 200:
        raise OdooError(f"{url} returned {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("count", "total", "size", "employees_count"):
            if isinstance(data.get(key), int):
                return data[key]
        for key in ("employees", "results", "data"):
            if isinstance(data.get(key), list):
                return len(data[key])
    raise OdooError(f"unrecognised response shape from {url}: {str(data)[:200]}")


def load_all(since):
    # A failed headcount lookup must not take the dashboard down with it: the
    # rest of the data is still worth showing. The error travels with the
    # payload so the page can say the denominator fell back rather than
    # printing a flattering number with no explanation.
    roster, headcount_error = None, None
    try:
        roster = fetch_department_roster()
    except OdooError as exc:
        headcount_error = str(exc)

    return {
        "tool_events": fetch_tool_events(since),
        "images": fetch_images(since),
        "profiles": fetch_profiles(),
        "headcount": roster["count"] if roster else None,
        "headcount_emails": roster["emails"] if roster else None,
        "headcount_error": headcount_error,
    }
