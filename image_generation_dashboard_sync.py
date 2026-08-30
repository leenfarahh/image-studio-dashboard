import hashlib
import json
import os
import sys
from datetime import date, datetime, timezone

import config
import datasource
import metrics
import render


def data_hash(dataset):
    """Fingerprint of the figures a dashboard actually shows.

    A served page polls this. Comparing content rather than build time means
    the page reloads only when a number really changed, so a periodic rebuild
    that finds nothing new does not yank the page out from under whoever is
    reading it.
    """
    payload = json.dumps(
        {
            "meta": dataset["meta"],
            "weeks": dataset["weeks"],
            "designers": dataset["designers"],
            "retention": dataset["retention"],
            "reliability": dataset["reliability"],
            "quality": dataset["quality"],
            "mix": dataset["mix"],
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_dataset(today=None):
    today = today or date.today()
    raw = datasource.load_all(config.LAUNCH_DATE)
    dataset = metrics.build(raw, config.LAUNCH_DATE, today)
    dataset["generated_at"] = datetime.now(timezone.utc).isoformat()
    dataset["data_hash"] = data_hash(dataset)
    return raw, dataset



def _write_atomic(path, text):
    """Write via a temp file then rename.

    Under gunicorn every worker rebuilds on its own schedule, so two of them
    can write the same file at once. A plain open(path, "w") would let a
    reader see a half-written page; os.replace is atomic.
    """
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def write_dashboards(dataset, out_dir=None, suffix=""):
    out_dir = out_dir or config.BASE_DIR
    paths = []
    for variant in config.VARIANTS:
        html = render.render_html(variant, dataset, config.NAV_ITEMS)
        path = os.path.join(out_dir, f"dashboard_{variant}{suffix}.html")
        _write_atomic(path, html)
        paths.append(path)

    summary = {
        "meta": dataset["meta"],
        "denominator": dataset["denominator"],
        "retention": dataset["retention"],
        "reliability": dataset["reliability"],
        "latency": dataset["latency"],
        "quality": dataset["quality"],
        "mix": dataset["mix"],
        "weeks": dataset["weeks"],
        "designers": dataset["designers"],
        "last_generated": dataset.get("generated_at") or datetime.now(timezone.utc).isoformat(),
        "data_hash": dataset.get("data_hash"),
    }
    summary_path = os.path.join(out_dir, f"dashboard_data{suffix}.json")
    _write_atomic(summary_path, json.dumps(summary, indent=2))
    paths.append(summary_path)
    return paths


def main():
    if not config.tool_configured():
        print(
            "Not configured. Set TOOL_SUPABASE_URL and TOOL_SUPABASE_API_KEY in .env,\n"
            "then re-run. Nothing was written."
        )
        sys.exit(1)

    _, dataset = build_dataset()
    meta = dataset["meta"]

    print(f"Tool events:       {meta['tool_event_count']}")
    print(f"Provisioned:       {meta['eligible_designers']}")
    print(f"Adoption:          {meta['tool_adoption_pct']}% "
          f"({meta['tool_adopters']}/{meta['eligible_designers']})")
    for prov in config.PROVIDERS:
        m = dataset["mix"][prov]
        print(f"  {config.PROVIDER_LABELS[prov]:<8} "
              f"{m['actions']:>4} actions  {m['users']} users  "
              f"{m['share_pct']}% of volume")
    print(f"Returning users:   {dataset['retention']['repeat_pct']}%")
    print(f"Success rate:      {dataset['reliability']['all']['success_pct']}%")
    print(f"Save rate:         {dataset['quality']['all']['save_pct']}%")

    for path in write_dashboards(dataset):
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
