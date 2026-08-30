"""Rendering layer: CSS, chart primitives, and the three dashboard templates.

Palette note: the categorical slots (ChatGPT blue, Gemini orange, violet accent),
the funnel's one-hue ordinal ramp, and the status steps were all run through the
data-viz validator in both light and dark mode. All six checks pass. Do not
re-step these by eye.
"""
import json
from datetime import datetime

import config

# ============================================================
# Styles
# ============================================================
CSS = """
<title>__TITLE__</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
  .dash {
    color-scheme: light;
    --surface: #fcfcfb;
    --plane: #f9f9f7;
    --ink: #0b0b0b;
    --ink-2: #52514e;
    --ink-muted: #898781;
    --grid: #e1e0d9;
    --baseline: #c3c2b7;
    --border: rgba(11,11,11,0.10);
    --chatgpt: #2a78d6;
    --chatgpt-tint: color-mix(in oklch, #2a78d6 55%, white);
    --gemini: #eb6834;
    --gemini-tint: color-mix(in oklch, #eb6834 55%, white);
    --accent: #4a3aa7;
    --accent-tint: color-mix(in oklch, #4a3aa7 15%, white);
    --tile-bg: #ffffff;
    /* ordinal ramp for the adoption funnel - one hue, monotone lightness */
    --step-1: #86b6ef;
    --step-2: #5598e7;
    --step-3: #2a78d6;
    --step-4: #184f95;
    /* status - always paired with an icon + label, never colour alone */
    --good: #0ca30c;
    --warning: #fab219;
    --critical: #d03b3b;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) .dash {
      color-scheme: dark;
      --surface: #1a1a19;
      --plane: #0d0d0d;
      --ink: #ffffff;
      --ink-2: #c3c2b7;
      --ink-muted: #898781;
      --grid: #2c2c2a;
      --baseline: #383835;
      --border: rgba(255,255,255,0.10);
      --chatgpt: #3987e5;
      --chatgpt-tint: color-mix(in oklch, #3987e5 55%, white 20%);
      --gemini: #d95926;
      --gemini-tint: color-mix(in oklch, #d95926 55%, white 20%);
      --accent: #9085e9;
      --accent-tint: color-mix(in oklch, #9085e9 18%, #1a1a19);
      --tile-bg: #202020;
      --step-1: #cde2fb;
      --step-2: #86b6ef;
      --step-3: #3987e5;
      --step-4: #184f95;
      --good: #0ca30c;
      --warning: #fab219;
      --critical: #d03b3b;
    }
  }
  :root[data-theme="dark"] .dash {
    color-scheme: dark;
    --surface: #1a1a19;
    --plane: #0d0d0d;
    --ink: #ffffff;
    --ink-2: #c3c2b7;
    --ink-muted: #898781;
    --grid: #2c2c2a;
    --baseline: #383835;
    --border: rgba(255,255,255,0.10);
    --chatgpt: #3987e5;
    --chatgpt-tint: color-mix(in oklch, #3987e5 55%, white 20%);
    --gemini: #d95926;
    --gemini-tint: color-mix(in oklch, #d95926 55%, white 20%);
    --accent: #9085e9;
    --accent-tint: color-mix(in oklch, #9085e9 18%, #1a1a19);
    --tile-bg: #202020;
    --step-1: #cde2fb;
    --step-2: #86b6ef;
    --step-3: #3987e5;
    --step-4: #184f95;
    --good: #0ca30c;
    --warning: #fab219;
    --critical: #d03b3b;
  }

  .dash {
    background: var(--plane);
    color: var(--ink);
    font-family: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 28px clamp(16px, 4vw, 48px) 56px;
    min-height: 100%;
    box-sizing: border-box;
  }
  .dash *, .dash *::before, .dash *::after { box-sizing: border-box; }
  .dash .mono { font-family: "IBM Plex Mono", ui-monospace, monospace; font-variant-numeric: tabular-nums; }

  .dash-header {
    display: flex; flex-wrap: wrap; justify-content: space-between;
    align-items: flex-start; gap: 16px; max-width: 1180px; margin: 0 auto 20px;
  }
  .dash-eyebrow {
    font-size: 12px; font-weight: 600; letter-spacing: 0.08em;
    text-transform: uppercase; color: var(--accent); margin: 0 0 6px;
  }
  .dash-title { font-size: clamp(22px, 3vw, 30px); font-weight: 700; margin: 0 0 6px; text-wrap: balance; }
  .dash-sub { font-size: 14px; color: var(--ink-2); margin: 0; max-width: 62ch; }
  .dash-nav { display: flex; gap: 6px; flex-wrap: wrap; }
  .dash-nav a, .dash-nav span {
    font-size: 12.5px; font-weight: 600; padding: 7px 12px; border-radius: 999px;
    border: 1px solid var(--border); color: var(--ink-2);
    text-decoration: none; white-space: nowrap;
  }
  .dash-nav .current { background: var(--accent-tint); color: var(--accent); border-color: transparent; }
  .dash-nav a:hover { border-color: var(--accent); color: var(--accent); }

  .kpi-row {
    max-width: 1180px; margin: 0 auto 20px; display: grid;
    grid-template-columns: repeat(4, 1fr); gap: 12px;
  }
  @media (max-width: 860px) { .kpi-row { grid-template-columns: repeat(2, 1fr); } }
  .kpi-tile { background: var(--tile-bg); border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px; }
  .kpi-tile.is-headline { border-color: var(--accent); box-shadow: inset 3px 0 0 var(--accent); }
  .kpi-label {
    font-size: 11.5px; font-weight: 600; letter-spacing: 0.04em;
    text-transform: uppercase; color: var(--ink-muted); margin: 0 0 8px;
  }
  .kpi-value { font-size: 28px; font-weight: 700; line-height: 1; margin: 0 0 6px; }
  .kpi-value .unit { font-size: 15px; font-weight: 600; color: var(--ink-muted); margin-left: 2px; }
  .kpi-note { font-size: 12.5px; color: var(--ink-2); margin: 0; }

  .panel {
    max-width: 1180px; margin: 0 auto 16px; background: var(--tile-bg);
    border: 1px solid var(--border); border-radius: 12px; padding: 18px 20px 14px;
  }
  .panel-row {
    max-width: 1180px; margin: 0 auto 16px; display: grid;
    grid-template-columns: 1.3fr 1fr; gap: 16px; align-items: start;
  }
  .panel-row.even { grid-template-columns: 1fr 1fr; }
  @media (max-width: 900px) { .panel-row, .panel-row.even { grid-template-columns: 1fr; } }
  .panel-row .panel { margin: 0; }
  .panel-head {
    display: flex; justify-content: space-between; align-items: baseline;
    gap: 10px; margin-bottom: 8px; flex-wrap: wrap;
  }
  .panel-title { font-size: 14.5px; font-weight: 700; margin: 0; }
  .panel-hint { font-size: 12.5px; color: var(--ink-muted); margin: 2px 0 12px; max-width: 70ch; }
  .panel-legend { display: flex; gap: 14px; font-size: 12.5px; color: var(--ink-2); }
  .legend-dot { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 5px; }

  .chart-wrap { position: relative; }
  .chart-tooltip {
    position: absolute; pointer-events: none; background: var(--ink); color: var(--surface);
    font-size: 12px; padding: 8px 10px; border-radius: 8px; line-height: 1.5;
    opacity: 0; transition: opacity 0.08s ease; white-space: nowrap; z-index: 5;
    box-shadow: 0 4px 14px rgba(0,0,0,0.18);
  }
  .chart-tooltip .tt-row { display: flex; align-items: center; gap: 6px; }
  .chart-tooltip .tt-date { font-weight: 700; margin-bottom: 2px; }

  /* funnel */
  .funnel { display: flex; flex-direction: column; gap: 10px; margin-top: 6px; }
  .funnel-step { display: grid; grid-template-columns: 168px 1fr auto; gap: 12px; align-items: center; }
  @media (max-width: 620px) { .funnel-step { grid-template-columns: 120px 1fr auto; } }
  .funnel-name { font-size: 12.5px; color: var(--ink-2); }
  .funnel-track { background: var(--grid); border-radius: 4px; height: 20px; overflow: hidden; }
  .funnel-fill { height: 100%; border-radius: 4px; min-width: 2px; }
  .funnel-val { font-size: 12.5px; font-weight: 700; white-space: nowrap; }
  .funnel-val .sub { color: var(--ink-muted); font-weight: 500; margin-left: 4px; }

  .share-bar { display: flex; height: 22px; border-radius: 6px; overflow: hidden; margin: 10px 0 10px; gap: 2px; }
  .share-bar div { border-radius: 3px; }
  .share-legend { display: flex; justify-content: space-between; font-size: 12.5px; color: var(--ink-2); }
  .share-legend .val { color: var(--ink); font-weight: 700; }

  /* stat list */
  .stat-list { display: flex; flex-direction: column; gap: 0; margin-top: 4px; }
  .stat-line {
    display: flex; justify-content: space-between; align-items: baseline;
    gap: 12px; padding: 9px 0; border-bottom: 1px solid var(--grid); font-size: 13px;
  }
  .stat-line:last-child { border-bottom: none; }
  .stat-line .lbl { color: var(--ink-2); }
  .stat-line .num { font-weight: 700; white-space: nowrap; }
  .stat-line .num .sub { color: var(--ink-muted); font-weight: 500; font-size: 12px; margin-left: 5px; }

  .pill {
    display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px;
    font-weight: 600; padding: 3px 8px; border-radius: 999px; white-space: nowrap;
  }
  .pill.good { background: color-mix(in oklch, var(--good) 16%, transparent); color: var(--good); }
  .pill.warn { background: color-mix(in oklch, var(--warning) 22%, transparent); color: var(--ink); }
  .pill.bad  { background: color-mix(in oklch, var(--critical) 16%, transparent); color: var(--critical); }
  .pill.mute { background: var(--grid); color: var(--ink-2); }

  .empty-state {
    border: 1px dashed var(--baseline); border-radius: 10px; padding: 18px 20px;
    color: var(--ink-2); font-size: 13px; line-height: 1.6; background: var(--plane);
  }
  .empty-state b { color: var(--ink); }
  .empty-state code {
    font-family: "IBM Plex Mono", monospace; font-size: 12px;
    background: var(--grid); padding: 1px 5px; border-radius: 4px;
  }

  details.table-toggle summary {
    cursor: pointer; font-size: 13px; font-weight: 600; color: var(--accent);
    list-style: none; display: inline-flex; align-items: center; gap: 5px;
  }
  details.table-toggle summary::-webkit-details-marker { display: none; }
  details.table-toggle summary::before { content: "\\25B8"; font-size: 10px; transition: transform 0.12s ease; }
  details.table-toggle[open] summary::before { transform: rotate(90deg); }
  .data-table-scroll { overflow-x: auto; margin-top: 10px; }
  table.data-table { width: 100%; border-collapse: collapse; font-size: 12.5px; min-width: 640px; }
  table.data-table th, table.data-table td {
    padding: 7px 10px; text-align: right; border-bottom: 1px solid var(--grid); white-space: nowrap;
  }
  table.data-table th:first-child, table.data-table td:first-child { text-align: left; }
  table.data-table th {
    color: var(--ink-muted); font-weight: 600; font-size: 11.5px;
    text-transform: uppercase; letter-spacing: 0.03em;
  }
  table.data-table tr.is-idle td { color: var(--ink-muted); }

  .dash-footer {
    max-width: 1180px; margin: 8px auto 0; font-size: 12px; color: var(--ink-muted);
    display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px;
  }

  /* Refresh controls. Hidden by default and revealed only when the page is
     being served by app.py, since a published artifact has no server to ask. */
  .refresh-bar {
    max-width: 1180px; margin: 0 auto 16px; display: flex; align-items: center;
    justify-content: space-between; gap: 12px; flex-wrap: wrap;
    background: var(--tile-bg); border: 1px solid var(--border);
    border-radius: 10px; padding: 9px 14px;
  }
  .refresh-status { display: inline-flex; align-items: center; gap: 8px;
    font-size: 12.5px; color: var(--ink-2); }
  .refresh-bar .dot {
    width: 7px; height: 7px; border-radius: 50%; background: var(--good);
    flex: none; box-shadow: 0 0 0 3px color-mix(in oklch, var(--good) 20%, transparent);
  }
  .refresh-bar.is-stale .dot { background: var(--warning);
    box-shadow: 0 0 0 3px color-mix(in oklch, var(--warning) 22%, transparent); }
  .refresh-bar.is-error .dot { background: var(--critical);
    box-shadow: 0 0 0 3px color-mix(in oklch, var(--critical) 20%, transparent); }
  .refresh-btn {
    font: 600 12.5px/1 "IBM Plex Sans", system-ui, sans-serif;
    color: var(--accent); background: transparent; cursor: pointer;
    border: 1px solid var(--border); border-radius: 999px; padding: 7px 14px;
  }
  .refresh-btn:hover:not(:disabled) { border-color: var(--accent); }
  .refresh-btn:disabled { opacity: .55; cursor: default; }

  svg.chart-svg { display: block; width: 100%; height: auto; }
  svg.chart-svg .grid-line { stroke: var(--grid); stroke-width: 1; }
  svg.chart-svg .baseline { stroke: var(--baseline); stroke-width: 1; }
  svg.chart-svg .axis-label { fill: var(--ink-muted); font-size: 10.5px; font-family: "IBM Plex Mono", monospace; }
  svg.chart-svg .crosshair { stroke: var(--ink-muted); stroke-width: 1; stroke-dasharray: 3 3; opacity: 0; }
</style>
"""

# ============================================================
# Chart primitives
# ============================================================
CHART_JS = r"""
<script>
(function(){
  const NS = "http://www.w3.org/2000/svg";
  function svgEl(tag, attrs) {
    const el = document.createElementNS(NS, tag);
    for (const k in attrs) el.setAttribute(k, attrs[k]);
    return el;
  }
  function fmt(n) { return Number(n).toLocaleString(); }

  function scaffold(root, W, H, padL, padR, padT, padB, data, niceMax, y) {
    const svg = svgEl("svg", {viewBox: "0 0 " + W + " " + H, class: "chart-svg", role: "img"});
    for (let g = 0; g <= 4; g++) {
      const gv = niceMax * g / 4, gy = y(gv);
      svg.appendChild(svgEl("line", {x1: padL, x2: W - padR, y1: gy, y2: gy,
        class: g === 0 ? "baseline" : "grid-line"}));
      const lbl = svgEl("text", {x: padL - 8, y: gy + 3, class: "axis-label", "text-anchor": "end"});
      lbl.textContent = fmt(Math.round(gv));
      svg.appendChild(lbl);
    }
    const n = data.length;
    const labelEvery = n > 8 ? Math.ceil(n / 8) : 1;
    const plotW = W - padL - padR;
    const stepX = n > 1 ? plotW / (n - 1) : plotW;
    data.forEach((d, i) => {
      if (i % labelEvery !== 0 && i !== n - 1) return;
      const anchor = i === n - 1 && n > 1 ? "end" : (i === 0 ? "start" : "middle");
      const lx = i === n - 1 && n > 1 ? W - padR : (i === 0 ? padL : padL + i * stepX);
      const lbl = svgEl("text", {x: lx, y: H - 6, class: "axis-label", "text-anchor": anchor});
      lbl.textContent = d.label;
      svg.appendChild(lbl);
    });
    return svg;
  }

  function attachHover(root, svg, W, padL, padT, plotW, plotH, n, stepX, rowsFor) {
    const crosshair = svgEl("line", {x1: 0, x2: 0, y1: padT, y2: padT + plotH, class: "crosshair"});
    svg.appendChild(crosshair);
    const wrap = document.createElement("div");
    wrap.className = "chart-wrap";
    wrap.appendChild(svg);
    const tooltip = document.createElement("div");
    tooltip.className = "chart-tooltip";
    wrap.appendChild(tooltip);
    root.appendChild(wrap);

    const overlay = svgEl("rect", {x: padL, y: padT, width: plotW, height: plotH, fill: "transparent"});
    overlay.style.cursor = "crosshair";
    svg.appendChild(overlay);

    overlay.addEventListener("mousemove", ev => {
      const rect = svg.getBoundingClientRect();
      const relX = ((ev.clientX - rect.left) / rect.width) * W;
      let i = Math.round((relX - padL) / stepX);
      i = Math.max(0, Math.min(n - 1, i));
      const px = padL + i * stepX;
      crosshair.setAttribute("x1", px);
      crosshair.setAttribute("x2", px);
      crosshair.style.opacity = 1;
      tooltip.innerHTML = rowsFor(i);
      tooltip.style.opacity = 1;
      const bbox = wrap.getBoundingClientRect();
      tooltip.style.left = Math.min((px / W) * bbox.width + 14, bbox.width - 160) + "px";
      tooltip.style.top = "8px";
    });
    overlay.addEventListener("mouseleave", () => {
      tooltip.style.opacity = 0;
      crosshair.style.opacity = 0;
    });
  }

  // Stacked area. A 2px surface-coloured separator sits on every internal
  // boundary so adjacent fills never bleed into one another.
  function renderStackedArea(root, data, series, opts) {
    opts = opts || {};
    const W = (opts && opts.width) || 1000, H = (opts && opts.height) || 260;
    const padL = 40, padR = 12, padT = 14, padB = 28;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const n = data.length;
    const stepX = n > 1 ? plotW / (n - 1) : plotW;

    let maxTotal = 0;
    data.forEach(d => {
      let sum = 0;
      series.forEach(s => sum += (d[s.key] || 0));
      if (sum > maxTotal) maxTotal = sum;
    });
    const niceMax = Math.ceil(Math.max(maxTotal, 4) * 1.15 / 4) * 4;

    const x = i => padL + i * stepX;
    const y = v => padT + plotH - (v / niceMax) * plotH;
    const svg = scaffold(root, W, H, padL, padR, padT, padB, data, niceMax, y);
    const surface = getComputedStyle(root).getPropertyValue("--tile-bg").trim() || "#fff";

    const cum = data.map(() => 0);
    series.forEach(s => {
      const botPts = data.map((d, i) => [x(i), y(cum[i])]);
      const prev = cum.slice();
      data.forEach((d, i) => { cum[i] += (d[s.key] || 0); });
      const topPts = data.map((d, i) => [x(i), y(cum[i])]);
      const pathPts = topPts.concat(botPts.slice().reverse());
      svg.appendChild(svgEl("path", {
        d: "M " + pathPts.map(p => p.join(",")).join(" L ") + " Z",
        fill: s.color, opacity: 0.9
      }));
      if (prev.some(v => v > 0)) {
        svg.appendChild(svgEl("path", {
          d: "M " + botPts.map(p => p.join(",")).join(" L "),
          fill: "none", stroke: surface, "stroke-width": 2
        }));
      }
      svg.appendChild(svgEl("path", {
        d: "M " + topPts.map(p => p.join(",")).join(" L "),
        fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linecap": "round"
      }));
      if (n === 1) {
        svg.appendChild(svgEl("circle", {cx: x(0), cy: y(cum[0]), r: 4, fill: s.color,
          stroke: surface, "stroke-width": 2}));
      }
    });

    attachHover(root, svg, W, padL, padT, plotW, plotH, n, stepX, i => {
      let rows = "";
      series.slice().reverse().forEach(s => {
        rows += '<div class="tt-row"><span class="legend-dot" style="background:' + s.color +
                '"></span>' + s.label + ': <b class="mono">&nbsp;' + fmt(data[i][s.key] || 0) + "</b></div>";
      });
      return '<div class="tt-date">' + data[i].label + "</div>" + rows;
    });
  }

  // Multi-line. Single shared y-axis - never a second scale.
  function renderLines(root, data, lines, opts) {
    opts = opts || {};
    // A chart in a half-width column renders its viewBox at roughly half the
    // pixel width, which shrinks axis text with it. Narrow panels pass a
    // smaller W so the labels keep close to their intended size.
    const W = opts.width || 1000, H = opts.height || 220;
    const padL = 40, padR = 12, padT = 14, padB = 28;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const n = data.length;
    const stepX = n > 1 ? plotW / (n - 1) : plotW;

    let maxV = 1;
    data.forEach(d => lines.forEach(l => { if ((d[l.key] || 0) > maxV) maxV = d[l.key]; }));
    const niceMax = opts.max || Math.ceil(maxV * 1.2 / 4) * 4 || 4;

    const x = i => padL + i * stepX;
    const y = v => padT + plotH - (v / niceMax) * plotH;
    const svg = scaffold(root, W, H, padL, padR, padT, padB, data, niceMax, y);
    const surface = getComputedStyle(root).getPropertyValue("--tile-bg").trim() || "#fff";

    lines.forEach(l => {
      const pts = data.map((d, i) => [x(i), y(d[l.key] || 0)]);
      const attrs = {d: "M " + pts.map(p => p.join(",")).join(" L "), fill: "none",
                     stroke: l.color, "stroke-width": 2, "stroke-linecap": "round"};
      if (l.dashed) attrs["stroke-dasharray"] = "5 4";
      svg.appendChild(svgEl("path", attrs));
      // 2px surface ring keeps overlapping end markers legible
      const last = pts[pts.length - 1];
      svg.appendChild(svgEl("circle", {cx: last[0], cy: last[1], r: 4.5, fill: l.color,
        stroke: surface, "stroke-width": 2}));
      if (n === 1) {
        svg.appendChild(svgEl("circle", {cx: pts[0][0], cy: pts[0][1], r: 4.5, fill: l.color,
          stroke: surface, "stroke-width": 2}));
      }
    });

    attachHover(root, svg, W, padL, padT, plotW, plotH, n, stepX, i => {
      let rows = "";
      lines.forEach(l => {
        rows += '<div class="tt-row"><span class="legend-dot" style="background:' + l.color +
                '"></span>' + l.label + ': <b class="mono">&nbsp;' + fmt(data[i][l.key] || 0) + "</b></div>";
      });
      return '<div class="tt-date">' + data[i].label + "</div>" + rows;
    });
  }

  window.__dashCharts = { renderStackedArea, renderLines };
})();
</script>
"""


# ============================================================
# HTML fragment helpers
# ============================================================
def esc(value):
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def kpi(label, value, note, unit="", headline=False):
    cls = "kpi-tile is-headline" if headline else "kpi-tile"
    unit_html = f'<span class="unit">{esc(unit)}</span>' if unit else ""
    return (
        f'<div class="{cls}">'
        f'<p class="kpi-label">{esc(label)}</p>'
        f'<p class="kpi-value mono">{esc(value)}{unit_html}</p>'
        f'<p class="kpi-note">{note}</p></div>'
    )


def funnel(steps):
    """steps: list of (name, count, note). Widths are relative to step one."""
    base = max(1, steps[0][1]) if steps else 1
    out = ['<div class="funnel">']
    for idx, (name, count, note) in enumerate(steps):
        width = max(1.5, 100.0 * count / base)
        color = f"var(--step-{min(idx + 1, 4)})"
        out.append(
            f'<div class="funnel-step">'
            f'<span class="funnel-name">{esc(name)}</span>'
            f'<div class="funnel-track"><div class="funnel-fill" '
            f'style="width:{width:.1f}%;background:{color}"></div></div>'
            f'<span class="funnel-val mono">{count}<span class="sub">{note}</span></span>'
            f"</div>"
        )
    out.append("</div>")
    return "".join(out)


def stat_lines(rows):
    out = ['<div class="stat-list">']
    for label, value, sub in rows:
        sub_html = f'<span class="sub">{sub}</span>' if sub else ""
        out.append(
            f'<div class="stat-line"><span class="lbl">{label}</span>'
            f'<span class="num mono">{value}{sub_html}</span></div>'
        )
    out.append("</div>")
    return "".join(out)


def table(headers, rows, row_classes=None):
    head = "<tr>" + "".join(f"<th>{esc(h)}</th>" for h in headers) + "</tr>"
    body = ""
    for i, r in enumerate(rows):
        cls = f' class="{row_classes[i]}"' if row_classes and row_classes[i] else ""
        cells = "".join(
            f'<td class="mono">{c}</td>' if j else f"<td>{c}</td>"
            for j, c in enumerate(r)
        )
        body += f"<tr{cls}>{cells}</tr>"
    return (
        '<div class="data-table-scroll"><table class="data-table">'
        f"<thead>{head}</thead><tbody>{body}</tbody></table></div>"
    )


def health_pill(pct, attempts=None, good_at=95.0, warn_at=85.0):
    # Zero attempts is not a health verdict, so it gets a neutral pill rather
    # than a green one computed from an empty sample.
    if attempts == 0:
        return '<span class="pill mute">No attempts yet</span>'
    if pct >= good_at:
        return f'<span class="pill good">&#10003; {pct}% healthy</span>'
    if pct >= warn_at:
        return f'<span class="pill warn">&#9888; {pct}% degraded</span>'
    return f'<span class="pill bad">&#10007; {pct}% failing</span>'


# ============================================================
# Dashboard templates
# ============================================================
TITLES = {
    "overall": (
        "Adoption",
        "Image Generator Adoption",
        "Image Generator - Tool Usage",
        "Every image generated through the MCP tool, both models combined. "
        "Measured against the designers provisioned on it.",
    ),
    "chatgpt": (
        "Adoption . ChatGPT",
        "ChatGPT Image Gen Adoption",
        "ChatGPT Image Generation",
        "Every image generated on ChatGPT through the MCP tool. "
        "Measured against the designers provisioned on it.",
    ),
    "gemini": (
        "Adoption . Gemini",
        "Gemini Image Gen Adoption",
        "Gemini Image Generation",
        "Every image generated on Gemini through the MCP tool. "
        "Measured against the designers provisioned on it.",
    ),
}


def _nav(nav_items, variant):
    """Cross-dashboard nav.

    The same file is served by app.py, opened straight off disk, and published
    as a Claude artifact. A single hardcoded href cannot satisfy all three, so
    the published artifact URL is the default and NAV_JS rewrites it to a local
    path when the page is being served locally.
    """
    out = ""
    for item in nav_items:
        label = esc(item["label"])
        if item["variant"] == variant:
            out += f'<span class="current">{label}</span>'
            continue
        target = item.get("url") or f'/dashboard/{item["variant"]}'
        out += (
            f'<a data-variant="{esc(item["variant"])}" '
            f'href="{esc(target)}">{label}</a>'
        )
    return out


NAV_JS = """
<script>
(function(){
  var loc = window.location;
  var links = document.querySelectorAll('.dash .dash-nav a[data-variant]');
  for (var i = 0; i < links.length; i++) {
    var v = links[i].getAttribute('data-variant');
    if (loc.protocol === 'file:') {
      links[i].setAttribute('href', 'dashboard_' + v + '.html');
    } else if (loc.pathname.indexOf('/dashboard/') === 0) {
      links[i].setAttribute('href', '/dashboard/' + v);
    }
    // Anywhere else (the published artifact) keeps the absolute URL.
  }
})();
</script>
"""

# Auto-refresh. Only activates when app.py is serving the page: a published
# artifact is a static snapshot with no server to ask, so the bar stays hidden
# rather than offering a button that cannot work.
REFRESH_JS = """
<script>
(function(){
  var root = document.querySelector('.dash[data-variant]');
  if (!root) return;
  var served = window.location.pathname.indexOf('/dashboard/') === 0;
  if (!served) return;

  var bar = root.querySelector('.refresh-bar');
  var btn = root.querySelector('.refresh-btn');
  var age = root.querySelector('.refresh-age');
  if (!bar || !btn || !age) return;
  bar.hidden = false;

  var pageHash = root.getAttribute('data-hash') || '';
  var generated = Date.parse(root.getAttribute('data-generated') || '') || Date.now();
  var pollMs = (parseInt(root.getAttribute('data-poll'), 10) || 30) * 1000;
  var busy = false;

  function describeAge() {
    var secs = Math.max(0, Math.round((Date.now() - generated) / 1000));
    if (secs < 60) return 'Updated just now';
    var mins = Math.round(secs / 60);
    if (mins < 60) return 'Updated ' + mins + ' min ago';
    var hrs = Math.round(mins / 60);
    if (hrs < 24) return 'Updated ' + hrs + (hrs === 1 ? ' hour ago' : ' hours ago');
    var days = Math.round(hrs / 24);
    return 'Updated ' + days + (days === 1 ? ' day ago' : ' days ago');
  }

  function paint() {
    if (busy) return;
    age.textContent = describeAge();
    bar.classList.toggle('is-stale', (Date.now() - generated) > 15 * 60 * 1000);
  }

  function check(force) {
    if (busy) return;
    busy = true;
    if (force) { btn.disabled = true; btn.textContent = 'Refreshing...'; age.textContent = 'Reading database...'; }
    fetch('/api/status' + (force ? '?refresh=1' : ''), {cache: 'no-store'})
      .then(function(r){ return r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)); })
      .then(function(s){
        bar.classList.remove('is-error');
        // Reload only when the figures actually differ, so a rebuild that
        // found nothing new does not interrupt whoever is reading.
        if (s.data_hash && s.data_hash !== pageHash) { window.location.reload(); return; }
        if (s.generated_at) generated = Date.parse(s.generated_at) || generated;
        busy = false;
        btn.disabled = false;
        btn.textContent = 'Refresh now';
        paint();
        if (force) { age.textContent = 'No change. ' + describeAge().toLowerCase(); }
      })
      .catch(function(){
        bar.classList.add('is-error');
        busy = false;
        btn.disabled = false;
        btn.textContent = 'Refresh now';
        age.textContent = 'Could not reach the server';
      });
  }

  btn.addEventListener('click', function(){ check(true); });
  paint();
  setInterval(paint, 15000);
  setInterval(function(){ check(false); }, pollMs);
  document.addEventListener('visibilitychange', function(){
    if (!document.hidden) check(false);
  });
})();
</script>
"""


def _shell(variant, dataset, nav_items, kpis_html, body_html, script_html):
    eyebrow, page_title, title, sub = TITLES[variant]
    meta = dataset["meta"]
    now = datetime.now()
    stamp = now.strftime("%b %d, %Y at %H:%M")
    window = f"{meta['launch_date']} to {meta['generated_through']}"
    generated_at = dataset.get("generated_at", "")
    dhash = dataset.get("data_hash", "")
    return f"""{CSS.replace("__TITLE__", page_title)}
<div class="dash" data-variant="{variant}"
     data-hash="{esc(dhash)}" data-generated="{esc(generated_at)}"
     data-poll="{config.POLL_SECONDS}">
  <div class="dash-header">
    <div>
      <p class="dash-eyebrow">{esc(eyebrow)}</p>
      <h1 class="dash-title">{esc(title)}</h1>
      <p class="dash-sub">{esc(sub)}</p>
    </div>
    <div class="dash-nav">{_nav(nav_items, variant)}</div>
  </div>

  <div class="refresh-bar" hidden>
    <span class="refresh-status">
      <span class="dot"></span>
      <span class="refresh-age">Updated just now</span>
    </span>
    <button type="button" class="refresh-btn">Refresh now</button>
  </div>

  <div class="kpi-row">{kpis_html}</div>

  {body_html}

  <div class="dash-footer">
    <span>Live from Supabase . window {esc(window)} . generated {esc(stamp)}</span>
    <span>Refresh: python image_generation_dashboard_sync.py</span>
  </div>
</div>

{NAV_JS}
{REFRESH_JS}
{CHART_JS}
{script_html}
"""


def _designer_table(dataset, scope):
    """scope: 'all' | 'chatgpt' | 'gemini'."""
    rows, classes = [], []
    for d in dataset["designers"]:
        n = d["tool_total"] if scope == "all" else d["tool_" + scope]
        if n == 0 and not d["provisioned"]:
            continue
        # Weeks and last-used must match the column scope, otherwise a
        # Gemini-only designer reads as "not started" beside a ChatGPT date.
        weeks = d["active_weeks_" + scope]
        last_seen = d["last_seen_" + scope]
        if n == 0:
            status = '<span class="pill mute">Not started</span>'
        elif weeks >= 2:
            status = '<span class="pill good">&#10003; Returning</span>'
        else:
            status = '<span class="pill warn">&#9888; Tried once</span>'

        if scope == "all":
            cells = [esc(d["name"]), d["tool_chatgpt"], d["tool_gemini"]]
        else:
            cells = [esc(d["name"]), n]
        rows.append(cells + [weeks, last_seen or "Never", status])
        classes.append("is-idle" if n == 0 else "")

    lead = ["Designer", "ChatGPT", "Gemini"] if scope == "all" else ["Designer", "Actions"]
    return table(lead + ["Active weeks", "Last used", "Status"], rows, classes)


def _weekly_table(dataset, variant):
    rows = []
    for w in dataset["weeks"]:
        if variant == "overall":
            rows.append([w["label"], w["tool_chatgpt_total"], w["tool_gemini_total"],
                         w["tool_active"], w["tool_cumulative"],
                         f'{w["tool_adoption_pct"]}%'])
        else:
            pre = "tool_" + variant
            rows.append([w["label"], w[pre + "_generate"], w[pre + "_refine"],
                         w[pre + "_total"], w[pre + "_active"],
                         w[pre + "_cumulative"], f'{w[variant + "_adoption_pct"]}%'])
    headers = (
        ["Week of", "ChatGPT", "Gemini", "Active users", "Cumulative adopters", "Adoption"]
        if variant == "overall" else
        ["Week of", "Generate", "Refine", "Total", "Active users",
         "Cumulative adopters", "Adoption"]
    )
    return (
        '<div class="panel"><details class="table-toggle">'
        "<summary>View weekly data table</summary>"
        + table(headers, rows) + "</details></div>"
    )


def _ms(value):
    """No samples means no time spent, so 0. Never a placeholder dash."""
    return f"{(value or 0) / 1000:.1f}s"


def render_overall(dataset, nav_items):
    meta, ret = dataset["meta"], dataset["retention"]
    rel, lat, qual = dataset["reliability"], dataset["latency"], dataset["quality"]
    weeks = dataset["weeks"]
    denom = dataset["denominator"]
    total_actions = sum(w["tool_total"] for w in weeks)
    chatgpt_total = sum(w["tool_chatgpt_total"] for w in weeks)
    gemini_total = sum(w["tool_gemini_total"] for w in weeks)
    split = chatgpt_total + gemini_total
    cg_pct = round(100 * chatgpt_total / split) if split else 0
    gm_pct = 100 - cg_pct if split else 0

    kpis = (
        kpi("Adoption rate", meta["tool_adoption_pct"], unit="%",
            note=f'{meta["tool_adopters"]} of {denom} provisioned designers have generated at least once',
            headline=True)
        + kpi("Returning users", ret["repeat_pct"], unit="%",
              note=f'{ret["repeat_users"]} of {ret["adopters"]} came back in a second week')
        + kpi("Total actions", f"{total_actions:,}",
              note="generate + refine through the tool, since launch")
        + kpi("Success rate", rel["all"]["success_pct"], unit="%",
              note=f'{rel["all"]["failed"]} failed of {rel["all"]["attempts"]} attempts')
    )

    funnel_html = funnel([
        ("Provisioned", denom, "designers"),
        ("Generated at least once", meta["tool_adopters"],
         f'{meta["tool_adoption_pct"]}%'),
        ("Came back a 2nd week", ret["repeat_users"], f'{ret["repeat_pct"]}%'),
        ("Kept an output", dataset["savers"]["all"],
         f'{round(100 * dataset["savers"]["all"] / max(1, denom))}%'),
    ])

    stickiness = stat_lines([
        ("Adopters", ret["adopters"], f'of {denom} provisioned'),
        ("Returning (2+ weeks)", ret["repeat_users"], f'{ret["repeat_pct"]}%'),
        ("Tried once, not since", ret["one_and_done"], f'{ret["one_and_done_pct"]}%'),
        ("Never started", ret["never_tried"], ""),
        ("Avg active weeks per adopter", ret["avg_active_weeks"], ""),
    ])

    err_rows = [[esc(code), n] for code, n in rel["all"]["errors"][:6]]
    errors_html = (
        table(["Error", "Count"], err_rows) if err_rows
        else '<p class="panel-hint">No failed attempts recorded in this window.</p>'
    )
    reliability_html = (
        f'<div class="panel-head"><p class="panel-title">Reliability &amp; speed</p>'
        f'{health_pill(rel["all"]["success_pct"], rel["all"]["attempts"])}</div>'
        + stat_lines([
            ("Attempts", f'{rel["all"]["attempts"]:,}', ""),
            ("Failed", rel["all"]["failed"], f'{rel["all"]["failure_pct"]}%'),
            ("ChatGPT median / p95", _ms(lat["chatgpt"]["p50"]),
             f'p95 {_ms(lat["chatgpt"]["p95"])}'),
            ("Gemini median / p95", _ms(lat["gemini"]["p50"]),
             f'p95 {_ms(lat["gemini"]["p95"])}'),
        ])
        + errors_html
    )

    quality_html = (
        '<div class="panel-head"><p class="panel-title">Did the output get used?</p></div>'
        '<p class="panel-hint">Generating is not the goal. A saved image is the '
        'only signal that a render was good enough to take into client work.</p>'
        + stat_lines([
            ("Images generated", f'{qual["all"]["images"]:,}', ""),
            ("Saved to library", qual["all"]["saved"], f'{qual["all"]["save_pct"]}%'),
            ("Refines per generate", qual["all"]["refines_per_generate"],
             f'{qual["all"]["refines"]} refines'),
        ])
    )

    body = f"""
  <div class="panel-row">
    <div class="panel">
      <div class="panel-head"><p class="panel-title">Adoption funnel</p></div>
      <p class="panel-hint">Each stage counts <b>people</b>, not actions. The drop
        between stages is where the rollout is actually losing designers.</p>
      {funnel_html}
    </div>
    <div class="panel">
      <div class="panel-head"><p class="panel-title">Stickiness</p></div>
      {stickiness}
    </div>
  </div>

  <div class="panel">
    <div class="panel-head">
      <p class="panel-title">Weekly volume by model</p>
      <div class="panel-legend">
        <span><span class="legend-dot" style="background:var(--chatgpt)"></span>ChatGPT</span>
        <span><span class="legend-dot" style="background:var(--gemini)"></span>Gemini</span>
      </div>
    </div>
    <div id="chart-volume"></div>
  </div>

  <div class="panel-row">
    <div class="panel">
      <div class="panel-head">
        <p class="panel-title">Active users &amp; cumulative adopters</p>
        <div class="panel-legend">
          <span><span class="legend-dot" style="background:var(--accent)"></span>Active / week</span>
          <span><span class="legend-dot" style="background:var(--ink-muted)"></span>Cumulative adopters</span>
        </div>
      </div>
      <div id="chart-users"></div>
    </div>
    <div class="panel">
      <div class="panel-head"><p class="panel-title">Model split</p></div>
      <div class="share-bar">
        <div style="width:{cg_pct}%; background:var(--chatgpt)"></div>
        <div style="width:{gm_pct}%; background:var(--gemini)"></div>
      </div>
      <div class="share-legend">
        <span>ChatGPT <span class="val mono">{chatgpt_total:,}</span></span>
        <span>Gemini <span class="val mono">{gemini_total:,}</span></span>
      </div>
      <p class="panel-hint" style="margin-top:14px">Share of all in-tool actions
        run on each model.</p>
    </div>
  </div>

  <div class="panel-row even">
    <div class="panel">{reliability_html}</div>
    <div class="panel">{quality_html}</div>
  </div>

  <div class="panel">
    <div class="panel-head"><p class="panel-title">By designer</p></div>
    <p class="panel-hint">Anyone provisioned but idle is listed too - that is the
      follow-up list for the rollout.</p>
    {_designer_table(dataset, "all")}
  </div>

  {_weekly_table(dataset, "overall")}
"""

    script = """
<script>
(function(){
  const data = __DATA__;
  const root = document.querySelector('.dash[data-variant="overall"]');
  const css = k => getComputedStyle(root).getPropertyValue(k).trim();
  window.__dashCharts.renderStackedArea(root.querySelector('#chart-volume'), data, [
    {key: "tool_chatgpt_total", label: "ChatGPT", color: css('--chatgpt')},
    {key: "tool_gemini_total",  label: "Gemini",  color: css('--gemini')}
  ]);
  window.__dashCharts.renderLines(root.querySelector('#chart-users'), data, [
    {key: "tool_active",     label: "Active / week",        color: css('--accent')},
    {key: "tool_cumulative", label: "Cumulative adopters",  color: css('--ink-muted'), dashed: true}
  ], {width: 560, height: 200});
})();
</script>
""".replace("__DATA__", json.dumps(dataset["weeks"]))

    return _shell("overall", dataset, nav_items, kpis, body, script)


def render_provider(variant, dataset, nav_items):
    """One model, inside the tool.

    The old version of this view compared in-tool against direct use. Nothing
    reports direct use per designer, so the comparison is gone and the question
    becomes how the model is actually used: who reaches for it, how much of the
    volume it carries, and how much rework each kept image costs.
    """
    mix = dataset["mix"]
    m, overlap = mix[variant], mix["overlap"]
    rel, lat, qual = dataset["reliability"], dataset["latency"], dataset["quality"]
    denom = dataset["denominator"]
    label = config.PROVIDER_LABELS[variant]
    other = [p for p in config.PROVIDERS if p != variant][0]
    other_label = config.PROVIDER_LABELS[other]

    kpis = (
        kpi(f"{label} adoption", m["adoption_pct"], unit="%",
            note=f'{m["users"]} of {denom} provisioned designers have generated on {label}',
            headline=True)
        + kpi("Share of volume", m["share_pct"], unit="%",
              note=f'{m["actions"]:,} of {overlap["total_actions"]:,} in-tool actions')
        + kpi("Save rate", qual[variant]["save_pct"], unit="%",
              note=f'{qual[variant]["saved"]} of {qual[variant]["images"]} images kept')
        + kpi("Success rate", rel[variant]["success_pct"], unit="%",
              note=f'{rel[variant]["attempts"]:,} attempts, {rel[variant]["failed"]} failed')
    )

    # A measured zero and a missing feed look identical on a chart, so say
    # which one this is rather than leaving the reader to guess.
    empty = (
        f'<div class="empty-state"><b>No {esc(label)} activity yet.</b> Nobody has '
        f'generated an image on {esc(label)} through the tool in this window. '
        f'Every figure below is a measured zero, not a missing feed.</div>'
        if m["actions"] == 0 else ""
    )

    adopters = stat_lines([
        (f"Used {label}", m["users"], f'{m["adoption_pct"]}%'),
        ("Kept an output", dataset["savers"][variant], ""),
        ("Used both models", overlap["both"], ""),
        (f"{label} only", overlap[variant + "_only"], f"never used {other_label}"),
        (f"Never used {label}", max(0, denom - m["users"]), ""),
    ])

    gen_pct = int(round(100.0 * m["generate"] / m["actions"])) if m["actions"] else 0
    ref_pct = 100 - gen_pct if m["actions"] else 0

    health_html = (
        f'<div class="panel-head"><p class="panel-title">{esc(label)} health</p>'
        f'{health_pill(rel[variant]["success_pct"], rel[variant]["attempts"])}</div>'
        + stat_lines([
            ("Actions", f'{m["actions"]:,}',
             f'{m["generate"]} generate / {m["refine"]} refine'),
            ("Attempts", f'{rel[variant]["attempts"]:,}', ""),
            ("Failed", rel[variant]["failed"], f'{rel[variant]["failure_pct"]}%'),
            ("Median latency", _ms(lat[variant]["p50"]), f'p95 {_ms(lat[variant]["p95"])}'),
            ("Images saved", qual[variant]["saved"], f'{qual[variant]["save_pct"]}%'),
            ("Refines per generate", qual[variant]["refines_per_generate"], ""),
        ])
    )

    body = f"""
  {empty}

  <div class="panel">
    <div class="panel-head">
      <p class="panel-title">Weekly {esc(label)} volume</p>
      <div class="panel-legend">
        <span><span class="legend-dot" style="background:var(--{variant})"></span>Generate</span>
        <span><span class="legend-dot" style="background:var(--ink-muted)"></span>Refine</span>
      </div>
    </div>
    <div id="chart-volume"></div>
  </div>

  <div class="panel-row">
    <div class="panel">
      <div class="panel-head">
        <p class="panel-title">Adopters per week</p>
        <div class="panel-legend">
          <span><span class="legend-dot" style="background:var(--{variant})"></span>Active / week</span>
          <span><span class="legend-dot" style="background:var(--ink-muted)"></span>Cumulative adopters</span>
        </div>
      </div>
      <div id="chart-users"></div>
    </div>
    <div class="panel">
      <div class="panel-head"><p class="panel-title">Generate vs refine</p></div>
      <div class="share-bar">
        <div style="width:{gen_pct}%; background:var(--{variant})"></div>
        <div style="width:{ref_pct}%; background:var(--ink-muted)"></div>
      </div>
      <div class="share-legend">
        <span>Generate <span class="val mono">{m["generate"]:,}</span></span>
        <span>Refine <span class="val mono">{m["refine"]:,}</span></span>
      </div>
      <p class="panel-hint" style="margin-top:14px">{qual[variant]["refines_per_generate"]}
        refines per generated image. A high ratio means {esc(label)} takes more
        reworking before anyone keeps the result.</p>
    </div>
  </div>

  <div class="panel-row even">
    <div class="panel">{health_html}</div>
    <div class="panel">
      <div class="panel-head"><p class="panel-title">Who uses {esc(label)}</p></div>
      {adopters}
    </div>
  </div>

  <div class="panel">
    <div class="panel-head"><p class="panel-title">By designer</p></div>
    <p class="panel-hint">{esc(label)} actions per designer, in the tool.</p>
    {_designer_table(dataset, variant)}
  </div>

  {_weekly_table(dataset, variant)}
"""

    script = """
<script>
(function(){
  const data = __DATA__;
  const root = document.querySelector('.dash[data-variant="__VARIANT__"]');
  const css = k => getComputedStyle(root).getPropertyValue(k).trim();
  window.__dashCharts.renderStackedArea(root.querySelector('#chart-volume'), data, [
    {key: "tool___VARIANT___generate", label: "Generate", color: css('--__VARIANT__')},
    {key: "tool___VARIANT___refine",   label: "Refine",   color: css('--ink-muted')}
  ]);
  window.__dashCharts.renderLines(root.querySelector('#chart-users'), data, [
    {key: "tool___VARIANT___active",     label: "Active / week",       color: css('--__VARIANT__')},
    {key: "tool___VARIANT___cumulative", label: "Cumulative adopters", color: css('--ink-muted'), dashed: true}
  ], {width: 560, height: 200});
})();
</script>
""".replace("__DATA__", json.dumps(dataset["weeks"])).replace("__VARIANT__", variant)

    return _shell(variant, dataset, nav_items, kpis, body, script)


def render_html(variant, dataset, nav_items):
    if variant == "overall":
        return render_overall(dataset, nav_items)
    return render_provider(variant, dataset, nav_items)
