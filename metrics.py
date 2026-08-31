"""Aggregation layer: turns raw rows into the numbers each view renders.

Every figure here describes image generation run through the MCP tool. That is
the only channel with per-designer data, so there is nothing to compare it
against and no "direct" column to fill.
"""
from collections import defaultdict
from datetime import datetime, timedelta

import config


def _week_start(d):
    return d - timedelta(days=d.weekday())


def _bucket_key(d, period):
    """The period a date falls in, as a sortable string.

    One function so a "distinct periods active" count means the same thing
    everywhere it is computed: retention, the designer table, the series.
    """
    return (_week_start(d) if period == "week" else d).isoformat()


def _pct(part, whole):
    return round(100.0 * part / whole, 1) if whole else 0.0


def _percentile(values, p):
    if not values:
        return 0
    ordered = sorted(values)
    k = (len(ordered) - 1) * (p / 100.0)
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    if lo == hi:
        return int(ordered[lo])
    return int(ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo))


def mark_retries(events, images):
    """Flag attempts a client retry replaced, on both events and images.

    Adds two flags to every row, which is the whole distinction the rest of
    this module counts on:

      superseded - the work completed but a retry replaced it, so nothing
                   reached the designer. A failure from where they sit, even
                   though the tool recorded a success.
      delivered  - the attempt succeeded AND reached the designer. This is
                   what "a generation" means everywhere downstream.

    The signature is a slow attempt followed by an identical prompt from the
    same person on the same model. Only the last render in such a run is
    delivered; the ones before it are what the client gave up waiting for.

    Detection needs the prompt, so an event with no image row, or one whose
    image predates the reporting window, stays delivered. This under-reports
    rather than inventing retries out of missing data.
    """
    prompt_by_image = {i["id"]: i.get("prompt") or "" for i in images}

    runs = defaultdict(list)
    for e in events:
        if not e.get("success", True):
            continue  # already a failure; there is nothing to supersede
        prompt = prompt_by_image.get(e.get("image_id"))
        if not prompt:
            continue
        runs[(e.get("user_id"), e["provider"], e["operation"], prompt)].append(e)

    for rows in runs.values():
        rows.sort(key=lambda r: r["ts"])
        for earlier, later in zip(rows, rows[1:]):
            gap = (later["ts"] - earlier["ts"]).total_seconds()
            slow = (earlier.get("latency_ms") or 0) >= config.CLIENT_TIMEOUT_MS
            if gap <= config.RETRY_WINDOW_SECONDS and slow:
                earlier["superseded"] = True

    for e in events:
        e.setdefault("superseded", False)
        e["delivered"] = bool(e.get("success", True)) and not e["superseded"]

    dropped = {e["image_id"] for e in events if e["superseded"] and e.get("image_id")}
    for i in images:
        i["superseded"] = i["id"] in dropped
        i["delivered"] = not i["superseded"]


def build_identity_map(profiles):
    """Map tool user UUIDs to a canonical person key (email where known)."""
    by_id, display = {}, {}
    for p in profiles:
        key = p["email"] or p["id"]
        by_id[p["id"]] = key
        display[key] = p["full_name"]
    return by_id, display


def person_key(event, id_to_email):
    """Events carry a profile UUID; resolve it to the email where known."""
    uid = event.get("user_id") or ""
    return id_to_email.get(uid, uid)


def build(raw, launch_date, today):
    events = raw["tool_events"]
    images = raw["images"]
    profiles = raw["profiles"]

    id_to_email, display_names = build_identity_map(profiles)
    eligible = [p for p in profiles if p["is_active"]]
    eligible_keys = {(p["email"] or p["id"]) for p in eligible}
    denominator = len(eligible_keys)

    for e in events:
        e["person"] = person_key(e, id_to_email)
        e["day"] = e["ts"].date()

    # Must run before anything counts an action: a retry writes a second
    # successful row, and without this every count below inflates.
    mark_retries(events, images)

    # ---------------------------------------------------------------
    # Daily series
    # ---------------------------------------------------------------
    by_day = defaultdict(list)
    for e in events:
        by_day[e["day"]].append(e)

    days = (today - launch_date).days + 1
    seen = defaultdict(set)
    seen_any = set()
    daily = []

    for offset in range(max(days, 1)):
        d = launch_date + timedelta(days=offset)
        rows = by_day.get(d, [])
        counts = defaultdict(int)
        actives = defaultdict(set)
        day_active = set()

        for e in rows:
            prov, op = e["provider"], e["operation"]
            # Volume counts what reached the designer. An attempt that failed,
            # or that a retry replaced, is still an attempt, but it is not a
            # generation and it does not make someone an active user of
            # something they never received.
            if e["delivered"]:
                counts[(prov, op)] += 1
                actives[prov].add(e["person"])
                seen[prov].add(e["person"])
                seen_any.add(e["person"])
                day_active.add(e["person"])

        # Same key shape as the weekly rows built below. The daily and weekly
        # views share every chart and table, so they have to share a schema;
        # only the bucket width differs.
        row = {"date": d.isoformat(), "label": d.strftime("%b") + " " + str(d.day)}
        for prov in config.PROVIDERS:
            pre = "tool_" + prov
            gen = counts[(prov, "generate")]
            ref = counts[(prov, "refine")]
            row[pre + "_generate"] = gen
            row[pre + "_refine"] = ref
            row[pre + "_total"] = gen + ref
            row[pre + "_active"] = len(actives[prov])
            row[pre + "_cumulative"] = len(seen[prov])
            row[prov + "_adoption_pct"] = _pct(len(seen[prov]), denominator)
        row["tool_total"] = sum(row["tool_" + p + "_total"] for p in config.PROVIDERS)
        row["tool_active"] = len(day_active)
        row["tool_cumulative"] = len(seen_any)
        row["tool_adoption_pct"] = _pct(len(seen_any), denominator)
        daily.append(row)

    # ---------------------------------------------------------------
    # Weekly series. Active users are DISTINCT people across the week,
    # not the max of the daily counts (which undercounts every week
    # where different people show up on different days).
    # ---------------------------------------------------------------
    week_people = defaultdict(lambda: defaultdict(set))
    week_counts = defaultdict(lambda: defaultdict(int))
    week_cum = {}

    for e in events:
        if not e["delivered"]:
            continue
        key = _bucket_key(e["day"], "week")
        week_counts[key][e["provider"] + "_" + e["operation"]] += 1
        week_people[key][e["provider"]].add(e["person"])
        week_people[key]["any"].add(e["person"])

    for row in daily:
        key = _bucket_key(datetime.fromisoformat(row["date"]).date(), "week")
        week_cum[key] = row

    week_keys = []
    cursor = _week_start(launch_date)
    end = _week_start(today)
    while cursor <= end:
        week_keys.append(cursor.isoformat())
        cursor += timedelta(days=7)

    weeks = []
    for key in week_keys:
        ws = datetime.fromisoformat(key).date()
        counts, people = week_counts[key], week_people[key]
        last = week_cum.get(key, {})
        w = {"week_start": key, "label": ws.strftime("%b") + " " + str(ws.day)}

        for prov in config.PROVIDERS:
            pre = "tool_" + prov
            gen = counts[prov + "_generate"]
            ref = counts[prov + "_refine"]
            w[pre + "_generate"] = gen
            w[pre + "_refine"] = ref
            w[pre + "_total"] = gen + ref
            w[pre + "_active"] = len(people.get(prov, ()))
            w[pre + "_cumulative"] = last.get(pre + "_cumulative", 0)
            # Per-provider adoption: share of provisioned designers who have
            # ever run this model through the tool.
            w[prov + "_adoption_pct"] = _pct(w[pre + "_cumulative"], denominator)

        w["tool_total"] = sum(w["tool_" + p + "_total"] for p in config.PROVIDERS)
        w["tool_active"] = len(people.get("any", ()))
        w["tool_cumulative"] = last.get("tool_cumulative", 0)
        w["tool_adoption_pct"] = _pct(w["tool_cumulative"], denominator)
        weeks.append(w)

    return {
        "meta": _build_meta(raw, launch_date, today, denominator, seen_any),
        "daily": daily,
        "weeks": weeks,
        "denominator": denominator,
        "reliability": _reliability(events),
        "latency": _latency(events),
        "quality": _quality(images),
        "savers": _savers(images, id_to_email),
        "retention": _retention(events, denominator),
        "designers": _designers(events, display_names, eligible_keys),
        "mix": _mix(events, images, denominator),
    }


def _build_meta(raw, launch_date, today, denominator, adopters):
    return {
        "launch_date": launch_date.isoformat(),
        "generated_through": today.isoformat(),
        "eligible_designers": denominator,
        "tool_adopters": len(adopters),
        "tool_adoption_pct": _pct(len(adopters), denominator),
        "tool_event_count": len(raw["tool_events"]),
    }


def _reliability(events):
    """Two flags, reported side by side: what got delivered and what did not.

    "Failed" is split, because the two halves are known to very different
    standards. Superseded attempts are measured: the rows are there and the
    retry that replaced them is there. Logged failures are whatever the tool
    chose to write down, and today it writes nothing on its failure path, so
    that count is a floor rather than a measurement. Reporting them as one
    number would let a missing feed pass for a clean record.
    """
    out = {}
    for scope in ["all"] + config.PROVIDERS:
        rows = events if scope == "all" else [e for e in events if e["provider"] == scope]
        total = len(rows)
        failed = sum(1 for e in rows if not e["success"])
        superseded = sum(1 for e in rows if e["superseded"])
        delivered = sum(1 for e in rows if e["delivered"])
        errors = defaultdict(int)
        for e in rows:
            if not e["success"]:
                errors[e.get("error_code") or "unknown"] += 1
        out[scope] = {
            "attempts": total,
            "delivered": delivered,
            "superseded": superseded,
            "failed": failed,
            "unusable": total - delivered,
            # No attempts means no evidence, so every rate is 0. Reporting
            # 100% delivered off zero calls would assert reliability that has
            # not been measured.
            "delivered_pct": _pct(delivered, total),
            "superseded_pct": _pct(superseded, total),
            "failed_pct": _pct(failed, total),
            "errors": sorted(errors.items(), key=lambda kv: -kv[1]),
            # True when the tool has never once written a failed row. That is
            # a claim about the feed, not about the service.
            "no_failure_feed": failed == 0,
        }
    return out


def _latency(events):
    out = {}
    for scope in ["all"] + config.PROVIDERS:
        # Superseded attempts are the slow ones by construction, so leaving
        # them in would report the timeout rather than the wait a designer
        # actually sat through.
        vals = [e["latency_ms"] for e in events
                if e["delivered"] and e.get("latency_ms")
                and (scope == "all" or e["provider"] == scope)]
        out[scope] = {"p50": _percentile(vals, 50), "p95": _percentile(vals, 95), "n": len(vals)}
    return out


def _quality(images):
    """Did the output actually get used? saved=true is the strongest signal,
    and refine chains show how much rework each keeper took."""
    out = {}
    for scope in ["all"] + config.PROVIDERS:
        rows = [i for i in images if i["delivered"]
                and (scope == "all" or i["provider"] == scope)]
        total = len(rows)
        saved = sum(1 for i in rows if i["saved"])
        roots = [i for i in rows if not i.get("parent_image_id")]
        refines = sum(1 for i in rows if i.get("parent_image_id"))
        out[scope] = {
            "images": total,
            "saved": saved,
            "save_pct": _pct(saved, total),
            "roots": len(roots),
            "refines": refines,
            "refines_per_generate": round(refines / len(roots), 2) if roots else 0.0,
        }
    return out


def _savers(images, id_to_email):
    """People who kept at least one output. The last funnel stage: generating
    is not the goal, walking away with a usable image is."""
    out = {}
    for scope in ["all"] + config.PROVIDERS:
        people = {
            id_to_email.get(i["user_id"], i["user_id"])
            for i in images
            if i["saved"] and i["delivered"]
            and (scope == "all" or i["provider"] == scope)
        }
        out[scope] = len(people)
    return out


def _retention(events, denominator):
    """Adoption is not 'tried once'. These measure whether people came back.

    Computed at both granularities, keyed by period. The two answer different
    questions and neither is a substitute for the other: a second week is the
    stricter test of a habit, but early in a rollout it cannot be passed yet,
    so a weekly-only read reports 0% returning while designers are in fact
    coming back the next day. Adopters and never-tried are the same number
    either way; only the repeat split moves.
    """
    out = {}
    for period in config.PERIODS:
        buckets_by_person = defaultdict(set)
        for e in events:
            if e["delivered"]:
                buckets_by_person[e["person"]].add(_bucket_key(e["day"], period))

        adopters = len(buckets_by_person)
        repeat = sum(1 for b in buckets_by_person.values() if len(b) >= 2)
        out[period] = {
            "adopters": adopters,
            "repeat_users": repeat,
            "repeat_pct": _pct(repeat, adopters),
            "one_and_done": adopters - repeat,
            "one_and_done_pct": _pct(adopters - repeat, adopters),
            "never_tried": max(0, denominator - adopters),
            "avg_active_periods": round(
                sum(len(b) for b in buckets_by_person.values()) / adopters, 2
            ) if adopters else 0.0,
        }
    return out


def _mix(events, images, denominator):
    """Per-provider shape of in-tool usage.

    This replaces the old tool-versus-direct comparison. With one channel the
    useful question is no longer where the work happened but how each model is
    used: how many people reach for it, how much of the volume it carries, and
    how much reworking an output takes before anyone keeps it.
    """
    ok = [e for e in events if e["delivered"]]
    total_actions = len(ok)

    out = {}
    for prov in config.PROVIDERS:
        rows = [e for e in ok if e["provider"] == prov]
        people = {e["person"] for e in rows}
        gen = sum(1 for e in rows if e["operation"] == "generate")
        ref = sum(1 for e in rows if e["operation"] == "refine")
        saved = sum(1 for i in images
                    if i["provider"] == prov and i["saved"] and i["delivered"])
        out[prov] = {
            "actions": len(rows),
            "generate": gen,
            "refine": ref,
            "users": len(people),
            "adoption_pct": _pct(len(people), denominator),
            "share_pct": _pct(len(rows), total_actions),
            "saved": saved,
            "refines_per_generate": round(ref / gen, 2) if gen else 0.0,
        }

    # Who reaches for both models, and who has settled on one.
    by_prov = {p: {e["person"] for e in ok if e["provider"] == p} for p in config.PROVIDERS}
    first, second = config.PROVIDERS[0], config.PROVIDERS[1]
    out["overlap"] = {
        "both": len(by_prov[first] & by_prov[second]),
        first + "_only": len(by_prov[first] - by_prov[second]),
        second + "_only": len(by_prov[second] - by_prov[first]),
        "total_actions": total_actions,
    }
    return out


def _designers(events, display_names, eligible_keys):
    """Per-person table. Includes provisioned designers with zero activity:
    on a rollout, the people who have not started are the actionable list.

    Active periods and last-used are tracked per provider as well as overall.
    A provider-filtered table that borrowed the overall figures would show
    someone who has only ever used Gemini as "not started" on the ChatGPT
    view while still printing a last-used date next to it.

    Both active-weeks and active-days are counted, because the status pill
    reads whichever period the reader has selected.
    """
    scopes = ["all"] + config.PROVIDERS

    def blank():
        return {
            "tool_chatgpt": 0, "tool_gemini": 0,
            "failed": 0, "superseded": 0,
            "buckets": {p: {s: set() for s in scopes} for p in config.PERIODS},
            "last_seen": {s: None for s in scopes},
        }

    stats = defaultdict(blank)

    for e in events:
        s = stats[e["person"]]
        if not e.get("success", True):
            s["failed"] += 1
            continue
        if e["superseded"]:
            # Counted against the person, not for them: they waited through
            # this one and got nothing back.
            s["superseded"] += 1
            continue
        s["tool_" + e["provider"]] += 1
        for scope in ("all", e["provider"]):
            for period in config.PERIODS:
                s["buckets"][period][scope].add(_bucket_key(e["day"], period))
            if s["last_seen"][scope] is None or e["day"] > s["last_seen"][scope]:
                s["last_seen"][scope] = e["day"]

    for key in eligible_keys:
        _ = stats[key]

    rows = []
    for key, s in stats.items():
        total = s["tool_chatgpt"] + s["tool_gemini"]
        row = {
            "person": key,
            "name": display_names.get(key, key),
            "tool_chatgpt": s["tool_chatgpt"],
            "tool_gemini": s["tool_gemini"],
            "tool_total": total,
            "total": total,
            "failed": s["failed"],
            "superseded": s["superseded"],
            "provisioned": key in eligible_keys,
        }
        for scope in scopes:
            seen = s["last_seen"][scope]
            row["active_weeks_" + scope] = len(s["buckets"]["week"][scope])
            row["active_days_" + scope] = len(s["buckets"]["day"][scope])
            row["last_seen_" + scope] = seen.isoformat() if seen else None
        # Back-compat aliases for the overall view.
        row["active_weeks"] = row["active_weeks_all"]
        row["active_days"] = row["active_days_all"]
        row["last_seen"] = row["last_seen_all"]
        rows.append(row)

    rows.sort(key=lambda r: (-r["total"], r["name"].lower()))
    return rows
