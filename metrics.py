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
            counts[(prov, op)] += 1
            # A failed attempt is still an attempt, but it does not make
            # someone an active user of something that did not work.
            if e.get("success", True):
                actives[prov].add(e["person"])
                seen[prov].add(e["person"])
                seen_any.add(e["person"])
                day_active.add(e["person"])

        row = {"date": d.isoformat()}
        for prov in config.PROVIDERS:
            pre = "tool_" + prov
            row[pre + "_generate"] = counts[(prov, "generate")]
            row[pre + "_refine"] = counts[(prov, "refine")]
            row[pre + "_active"] = len(actives[prov])
            row[pre + "_cumulative"] = len(seen[prov])
        row["tool_active"] = len(day_active)
        row["tool_cumulative"] = len(seen_any)
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
        key = _week_start(e["day"]).isoformat()
        week_counts[key][e["provider"] + "_" + e["operation"]] += 1
        if e.get("success", True):
            week_people[key][e["provider"]].add(e["person"])
            week_people[key]["any"].add(e["person"])

    for row in daily:
        key = _week_start(datetime.fromisoformat(row["date"]).date()).isoformat()
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
    out = {}
    for scope in ["all"] + config.PROVIDERS:
        rows = events if scope == "all" else [e for e in events if e["provider"] == scope]
        total = len(rows)
        failed = sum(1 for e in rows if not e["success"])
        errors = defaultdict(int)
        for e in rows:
            if not e["success"]:
                errors[e.get("error_code") or "unknown"] += 1
        out[scope] = {
            "attempts": total,
            "succeeded": total - failed,
            "failed": failed,
            # No attempts means no evidence, so both rates are 0. Reporting
            # 100% success off zero calls would assert reliability that has
            # not been measured.
            "success_pct": _pct(total - failed, total),
            "failure_pct": _pct(failed, total),
            "errors": sorted(errors.items(), key=lambda kv: -kv[1]),
        }
    return out


def _latency(events):
    out = {}
    for scope in ["all"] + config.PROVIDERS:
        vals = [e["latency_ms"] for e in events
                if e["success"] and e.get("latency_ms")
                and (scope == "all" or e["provider"] == scope)]
        out[scope] = {"p50": _percentile(vals, 50), "p95": _percentile(vals, 95), "n": len(vals)}
    return out


def _quality(images):
    """Did the output actually get used? saved=true is the strongest signal,
    and refine chains show how much rework each keeper took."""
    out = {}
    for scope in ["all"] + config.PROVIDERS:
        rows = [i for i in images if scope == "all" or i["provider"] == scope]
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
            if i["saved"] and (scope == "all" or i["provider"] == scope)
        }
        out[scope] = len(people)
    return out


def _retention(events, denominator):
    """Adoption is not 'tried once'. These measure whether people came back."""
    weeks_by_person = defaultdict(set)
    for e in events:
        if e.get("success", True):
            weeks_by_person[e["person"]].add(_week_start(e["day"]).isoformat())

    adopters = len(weeks_by_person)
    repeat = sum(1 for w in weeks_by_person.values() if len(w) >= 2)
    return {
        "adopters": adopters,
        "repeat_users": repeat,
        "repeat_pct": _pct(repeat, adopters),
        "one_and_done": adopters - repeat,
        "one_and_done_pct": _pct(adopters - repeat, adopters),
        "never_tried": max(0, denominator - adopters),
        "avg_active_weeks": round(sum(len(w) for w in weeks_by_person.values()) / adopters, 2)
        if adopters else 0.0,
    }


def _mix(events, images, denominator):
    """Per-provider shape of in-tool usage.

    This replaces the old tool-versus-direct comparison. With one channel the
    useful question is no longer where the work happened but how each model is
    used: how many people reach for it, how much of the volume it carries, and
    how much reworking an output takes before anyone keeps it.
    """
    ok = [e for e in events if e.get("success", True)]
    total_actions = len(ok)

    out = {}
    for prov in config.PROVIDERS:
        rows = [e for e in ok if e["provider"] == prov]
        people = {e["person"] for e in rows}
        gen = sum(1 for e in rows if e["operation"] == "generate")
        ref = sum(1 for e in rows if e["operation"] == "refine")
        saved = sum(1 for i in images if i["provider"] == prov and i["saved"])
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

    Active weeks and last-used are tracked per provider as well as overall.
    A provider-filtered table that borrowed the overall figures would show
    someone who has only ever used Gemini as "not started" on the ChatGPT
    view while still printing a last-used date next to it.
    """
    def blank():
        return {
            "tool_chatgpt": 0, "tool_gemini": 0,
            "failed": 0,
            "weeks": {scope: set() for scope in ["all"] + config.PROVIDERS},
            "last_seen": {scope: None for scope in ["all"] + config.PROVIDERS},
        }

    stats = defaultdict(blank)

    for e in events:
        s = stats[e["person"]]
        if not e.get("success", True):
            s["failed"] += 1
            continue
        s["tool_" + e["provider"]] += 1
        week = _week_start(e["day"]).isoformat()
        for scope in ("all", e["provider"]):
            s["weeks"][scope].add(week)
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
            "provisioned": key in eligible_keys,
        }
        for scope in ["all"] + config.PROVIDERS:
            seen = s["last_seen"][scope]
            row["active_weeks_" + scope] = len(s["weeks"][scope])
            row["last_seen_" + scope] = seen.isoformat() if seen else None
        # Back-compat aliases for the overall view.
        row["active_weeks"] = row["active_weeks_all"]
        row["last_seen"] = row["last_seen_all"]
        rows.append(row)

    rows.sort(key=lambda r: (-r["total"], r["name"].lower()))
    return rows
