"""Aggregation layer: turns raw rows into the numbers each dashboard renders."""
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
    uid = event.get("user_id") or ""
    if event["source"] == "tool":
        return id_to_email.get(uid, uid)
    return uid.strip().lower()


def build(raw, launch_date, today):
    tool_events = raw["tool_events"]
    direct_events = raw["standalone_events"]
    images = raw["images"]
    profiles = raw["profiles"]

    id_to_email, display_names = build_identity_map(profiles)
    eligible = [p for p in profiles if p["is_active"]]
    eligible_keys = {(p["email"] or p["id"]) for p in eligible}
    denominator = len(eligible_keys)

    all_events = tool_events + direct_events
    for e in all_events:
        e["person"] = person_key(e, id_to_email)
        e["day"] = e["ts"].date()

    # ---------------------------------------------------------------
    # Daily series
    # ---------------------------------------------------------------
    by_day = defaultdict(list)
    for e in all_events:
        by_day[e["day"]].append(e)

    days = (today - launch_date).days + 1
    seen = defaultdict(set)
    seen_tool_any, seen_direct_any, seen_any = set(), set(), set()
    daily = []

    for offset in range(max(days, 1)):
        d = launch_date + timedelta(days=offset)
        rows = by_day.get(d, [])
        counts = defaultdict(int)
        actives = defaultdict(set)
        day_tool_active, day_direct_active = set(), set()

        for e in rows:
            src, prov, op = e["source"], e["provider"], e["operation"]
            counts[(src, prov, op)] += 1
            if e.get("success", True):
                actives[(src, prov)].add(e["person"])
                seen[(src, prov)].add(e["person"])
                seen_any.add(e["person"])
                if src == "tool":
                    day_tool_active.add(e["person"])
                    seen_tool_any.add(e["person"])
                else:
                    day_direct_active.add(e["person"])
                    seen_direct_any.add(e["person"])

        row = {"date": d.isoformat()}
        for src in ("tool", "direct"):
            for prov in config.PROVIDERS:
                pre = src + "_" + prov
                row[pre + "_generate"] = counts[(src, prov, "generate")]
                row[pre + "_refine"] = counts[(src, prov, "refine")]
                row[pre + "_active"] = len(actives[(src, prov)])
                row[pre + "_cumulative"] = len(seen[(src, prov)])
        row["tool_active"] = len(day_tool_active)
        row["direct_active"] = len(day_direct_active)
        row["tool_cumulative"] = len(seen_tool_any)
        row["direct_cumulative"] = len(seen_direct_any)
        row["overall_cumulative"] = len(seen_any)
        daily.append(row)

    # ---------------------------------------------------------------
    # Weekly series. Active users are DISTINCT people across the week,
    # not the max of the daily counts (which undercounts every week
    # where different people show up on different days).
    # ---------------------------------------------------------------
    week_people = defaultdict(lambda: defaultdict(set))
    week_counts = defaultdict(lambda: defaultdict(int))
    week_cum = {}

    for e in all_events:
        key = _week_start(e["day"]).isoformat()
        src, prov, op = e["source"], e["provider"], e["operation"]
        week_counts[key][src + "_" + prov + "_" + op] += 1
        if e.get("success", True):
            week_people[key][src + "_" + prov].add(e["person"])
            week_people[key][src].add(e["person"])
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

        for src in ("tool", "direct"):
            for prov in config.PROVIDERS:
                pre = src + "_" + prov
                gen = counts[pre + "_generate"]
                ref = counts[pre + "_refine"]
                w[pre + "_generate"] = gen
                w[pre + "_refine"] = ref
                w[pre + "_total"] = gen + ref
                w[pre + "_active"] = len(people.get(pre, ()))
                w[pre + "_cumulative"] = last.get(pre + "_cumulative", 0)
            w[src + "_total"] = sum(w[src + "_" + p + "_total"] for p in config.PROVIDERS)
            w[src + "_active"] = len(people.get(src, ()))
            w[src + "_cumulative"] = last.get(src + "_cumulative", 0)

        w["overall_total"] = w["tool_total"] + w["direct_total"]
        w["overall_active"] = len(people.get("any", ()))
        w["overall_cumulative"] = last.get("overall_cumulative", 0)

        # Adoption rate: share of provisioned designers who have ever used it.
        w["tool_adoption_pct"] = _pct(w["tool_cumulative"], denominator)
        for prov in config.PROVIDERS:
            w[prov + "_direct_adoption_pct"] = _pct(w["direct_" + prov + "_cumulative"], denominator)
            w[prov + "_tool_adoption_pct"] = _pct(w["tool_" + prov + "_cumulative"], denominator)
        weeks.append(w)

    return {
        "meta": _build_meta(raw, launch_date, today, denominator,
                            seen_tool_any, seen_direct_any, seen_any),
        "daily": daily,
        "weeks": weeks,
        "denominator": denominator,
        "reliability": _reliability(tool_events),
        "latency": _latency(tool_events),
        "quality": _quality(images),
        "savers": _savers(images, id_to_email),
        "retention": _retention(all_events, denominator),
        "designers": _designers(all_events, display_names, eligible_keys),
        "substitution": _substitution(all_events, eligible_keys),
    }


def _build_meta(raw, launch_date, today, denominator, tool_any, direct_any, any_):
    return {
        "launch_date": launch_date.isoformat(),
        "generated_through": today.isoformat(),
        "eligible_designers": denominator,
        "tool_adopters": len(tool_any),
        "direct_adopters": len(direct_any),
        "overall_adopters": len(any_),
        "tool_adoption_pct": _pct(len(tool_any), denominator),
        "direct_adoption_pct": _pct(len(direct_any), denominator),
        "tool_event_count": len(raw["tool_events"]),
        "direct_event_count": len(raw["standalone_events"]),
        "standalone_connected": config.standalone_configured(),
    }


def _reliability(tool_events):
    out = {}
    for scope in ["all"] + config.PROVIDERS:
        rows = tool_events if scope == "all" else [e for e in tool_events if e["provider"] == scope]
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


def _latency(tool_events):
    out = {}
    for scope in ["all"] + config.PROVIDERS:
        vals = [e["latency_ms"] for e in tool_events
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


def _retention(all_events, denominator):
    """Adoption is not 'tried once'. These measure whether people came back."""
    weeks_by_person = defaultdict(set)
    for e in all_events:
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


def _substitution(all_events, eligible_keys):
    """Tool vs. direct. The point of dashboards 2 and 3: are designers running
    image generation through the tool, or still going straight to the vendor?"""
    out = {}
    for prov in config.PROVIDERS:
        rows = [e for e in all_events if e["provider"] == prov and e.get("success", True)]
        tool_rows = [e for e in rows if e["source"] == "tool"]
        direct_rows = [e for e in rows if e["source"] == "direct"]
        tool_people = {e["person"] for e in tool_rows}
        direct_people = {e["person"] for e in direct_rows}
        total_actions = len(tool_rows) + len(direct_rows)
        out[prov] = {
            "tool_actions": len(tool_rows),
            "direct_actions": len(direct_rows),
            "total_actions": total_actions,
            "tool_share_pct": _pct(len(tool_rows), total_actions),
            "direct_share_pct": _pct(len(direct_rows), total_actions),
            "tool_users": len(tool_people),
            "direct_users": len(direct_people),
            "both": len(tool_people & direct_people),
            "direct_only": len(direct_people - tool_people),
            "tool_only": len(tool_people - direct_people),
            "unknown_direct_users": len(direct_people - eligible_keys),
        }
    return out


def _designers(all_events, display_names, eligible_keys):
    """Per-person table. Includes provisioned designers with zero activity:
    on a rollout, the people who have not started are the actionable list.

    Active weeks and last-used are tracked per provider as well as overall.
    A provider-filtered table that borrowed the overall figures would show
    someone who has only ever used Gemini as "not started" on the ChatGPT
    page while still printing a last-used date next to it.
    """
    def blank():
        return {
            "tool_chatgpt": 0, "tool_gemini": 0,
            "direct_chatgpt": 0, "direct_gemini": 0,
            "failed": 0,
            "weeks": {scope: set() for scope in ["all"] + config.PROVIDERS},
            "last_seen": {scope: None for scope in ["all"] + config.PROVIDERS},
        }

    stats = defaultdict(blank)

    for e in all_events:
        s = stats[e["person"]]
        if not e.get("success", True):
            s["failed"] += 1
            continue
        s[e["source"] + "_" + e["provider"]] += 1
        week = _week_start(e["day"]).isoformat()
        for scope in ("all", e["provider"]):
            s["weeks"][scope].add(week)
            if s["last_seen"][scope] is None or e["day"] > s["last_seen"][scope]:
                s["last_seen"][scope] = e["day"]

    for key in eligible_keys:
        _ = stats[key]

    rows = []
    for key, s in stats.items():
        tool_total = s["tool_chatgpt"] + s["tool_gemini"]
        direct_total = s["direct_chatgpt"] + s["direct_gemini"]
        row = {
            "person": key,
            "name": display_names.get(key, key),
            "tool_chatgpt": s["tool_chatgpt"],
            "tool_gemini": s["tool_gemini"],
            "direct_chatgpt": s["direct_chatgpt"],
            "direct_gemini": s["direct_gemini"],
            "tool_total": tool_total,
            "direct_total": direct_total,
            "total": tool_total + direct_total,
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
