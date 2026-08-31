"""Step-by-step diagnostic for the Odoo headcount lookup.

Run this when the dashboard denominator falls back to provisioned profiles:

    python debug_odoo.py

It walks the same path datasource.fetch_headcount_from_odoo takes and prints
where it stops. Nothing is written and nothing is mutated - every call is a
read. Secrets are masked in the output so it is safe to paste into a ticket.
"""
import sys
import xmlrpc.client

import config
import datasource


def mask(value):
    if not value:
        return "(not set)"
    return f"{value[:4]}...{value[-2:]} ({len(value)} chars)"


def step(n, text):
    print(f"\n[{n}] {text}")


def fail(text, hint=None):
    print(f"    FAIL  {text}")
    if hint:
        print(f"    HINT  {hint}")
    sys.exit(1)


def ok(text):
    print(f"    OK    {text}")


print("=" * 68)
print("Odoo headcount diagnostic")
print("=" * 68)

step(1, "Configuration")
print(f"    ODOO_URL       {config.ODOO_URL or '(not set)'}")
print(f"    ODOO_DB        {config.ODOO_DB or '(not set)'}")
print(f"    ODOO_USERNAME  {config.ODOO_USERNAME or '(not set)'}")
print(f"    ODOO_API_KEY   {mask(config.ODOO_API_KEY)}")
print(f"    ODOO_DEPARTMENT {config.ODOO_DEPARTMENT!r}")
print(f"    sub-departments included: {config.ODOO_INCLUDE_SUB_DEPARTMENTS}")
print(f"    ODOO_API_URL   {config.ODOO_API_URL or '(not set - XML-RPC path)'}")

if config.odoo_rest_configured():
    step(2, "REST override is set, testing that instead of XML-RPC")
    try:
        print(f"    headcount = {datasource._fetch_headcount_rest()}")
    except datasource.OdooError as exc:
        fail(str(exc), "Unset ODOO_API_URL to use the stock XML-RPC API.")
    sys.exit(0)

if not config.odoo_configured():
    missing = [n for n in ("ODOO_URL", "ODOO_DB", "ODOO_USERNAME", "ODOO_API_KEY")
               if not getattr(config, n)]
    fail(
        "missing " + ", ".join(missing),
        "Add them to .env. ODOO_URL is the base instance URL with no /api "
        "suffix; on Odoo Online ODOO_DB is usually the subdomain.",
    )

step(2, f"Reaching {config.ODOO_URL}/xmlrpc/2/common")
common = xmlrpc.client.ServerProxy(f"{config.ODOO_URL}/xmlrpc/2/common", allow_none=True)
try:
    version = common.version()
except Exception as exc:
    fail(str(exc), "Check the URL, VPN/IP allowlist, and that it is the base "
                   "instance URL (no trailing path).")
ok(f"Odoo {version.get('server_version', '?')}")

step(3, f"Authenticating {config.ODOO_USERNAME} against database {config.ODOO_DB!r}")
try:
    uid = common.authenticate(config.ODOO_DB, config.ODOO_USERNAME, config.ODOO_API_KEY, {})
except xmlrpc.client.Fault as exc:
    fail(exc.faultString.strip(), "Usually a wrong ODOO_DB.")
if not uid:
    fail("authenticate returned no uid",
         "The login or the API key is wrong. Generate a key under "
         "Settings > My Profile > Account Security > New API Key, and use the "
         "same user's login email.")
ok(f"uid = {uid}")

models = xmlrpc.client.ServerProxy(f"{config.ODOO_URL}/xmlrpc/2/object", allow_none=True)


def call(model, method, *args, **kwargs):
    return models.execute_kw(
        config.ODOO_DB, uid, config.ODOO_API_KEY, model, method, list(args), kwargs
    )


step(4, "Reading hr.department")
try:
    departments = call("hr.department", "search_read", [], fields=["name", "parent_id"], limit=100)
except xmlrpc.client.Fault as exc:
    fail(exc.faultString.strip().splitlines()[-1],
         "This user has no HR access. Add it to the Employees app in Odoo, or "
         "use an API key belonging to a user who has it.")
ok(f"{len(departments)} departments visible")
for d in sorted(departments, key=lambda x: x["name"]):
    parent = d["parent_id"][1] if d.get("parent_id") else "-"
    print(f"          {d['id']:>4}  {d['name']}   (parent: {parent})")

step(5, f"Matching department {config.ODOO_DEPARTMENT!r}")
matches = [d for d in departments if d["name"].lower() == config.ODOO_DEPARTMENT.lower()]
if not matches:
    fail(f"no department is named {config.ODOO_DEPARTMENT!r}",
         "Set ODOO_DEPARTMENT to one of the names listed above (exact match, "
         "case-insensitive).")
ok(f"matched ids {[d['id'] for d in matches]}")

dept_ids = [d["id"] for d in matches]
if config.ODOO_INCLUDE_SUB_DEPARTMENTS:
    dept_ids = call("hr.department", "search", [("id", "child_of", dept_ids)])
    ok(f"with sub-departments: {dept_ids}")

step(6, "Counting employees")
domain = [("department_id", "in", dept_ids)]
model_used = "hr.employee"
try:
    count = call("hr.employee", "search_count", domain)
except xmlrpc.client.Fault as exc:
    print(f"    NOTE  hr.employee refused: {exc.faultString.strip().splitlines()[-1]}")
    print("    NOTE  falling back to hr.employee.public")
    model_used = "hr.employee.public"
    try:
        count = call("hr.employee.public", "search_count", domain)
    except xmlrpc.client.Fault as exc2:
        fail(exc2.faultString.strip().splitlines()[-1],
             "The API user cannot read employees at all.")
ok(f"{count} employees in {config.ODOO_DEPARTMENT!r} (via {model_used})")

step(7, "Roster (name + job title), to sanity-check who is being counted")
people = call(model_used, "search_read", domain,
              fields=["name", "job_title", "department_id"], limit=200)
for p in sorted(people, key=lambda x: x["name"]):
    dept = p["department_id"][1] if p.get("department_id") else "-"
    print(f"          {p['name']:<32} {(p.get('job_title') or '-'):<28} {dept}")

print("\n" + "=" * 68)
print(f"RESULT: headcount = {count}")
print(f"The dashboard currently uses {len(datasource.fetch_profiles())} provisioned "
      "profiles when this lookup is unavailable.")
print("=" * 68)
