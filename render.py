"""Rendering layer: CSS, chart primitives, and the three dashboard templates.

Palette note: the categorical slots (ChatGPT blue, Gemini orange, violet accent),
the funnel's one-hue ordinal ramp, and the status steps were all run through the
data-viz validator in both light and dark mode. All six checks pass. Do not
re-step these by eye.
"""
import json
from datetime import datetime

import assets
import config

# ============================================================
# Styles
# ============================================================
CSS = """
<title>__TITLE__</title>
__FAVICON__
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700;800&display=swap">
<style>
  .dash {
    color-scheme: light;
    --surface: #fdfcfb;
    --plane: #f5efe8;
    --ink: #002528;
    --ink-2: #425a5d;
    --ink-muted: #728486;
    --grid: #e6ddd2;
    --baseline: #cdbfae;
    --border: rgba(0,37,40,0.12);
    --chatgpt: #00939f;
    --chatgpt-tint: #67bec6;
    --gemini: #c65d26;
    --gemini-tint: #e69875;
    --accent: #002528;
    --accent-tint: #b6edf3;
    --sand: #e3d8cc;
    --tile-bg: #ffffff;
    /* ordinal ramp for the adoption funnel - brand teal, monotone lightness */
    --step-1: #6ac1c9;
    --step-2: #34a4ad;
    --step-3: #008994;
    --step-4: #00616a;
    /* status - reserved meaning, always paired with an icon + label */
    --good: #0ca30c;
    --warning: #fab219;
    --critical: #d03b3b;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) .dash {
      color-scheme: dark;
      --surface: #12292b;
      --plane: #0a1c1e;
      --ink: #eef8f9;
      --ink-2: #acc3c5;
      --ink-muted: #839698;
      --grid: #1f3c3f;
      --baseline: #2f5559;
      --border: rgba(182,237,243,0.14);
      --chatgpt: #00a1ac;
      --chatgpt-tint: #74cbd3;
      --gemini: #cd632d;
      --gemini-tint: #f0a27f;
      --accent: #b6edf3;
      --accent-tint: #0e3c40;
      --sand: #3a332c;
      --tile-bg: #173235;
      --step-1: #7ccdd5;
      --step-2: #40b1ba;
      --step-3: #00939f;
      --step-4: #006d76;
      --good: #0ca30c;
      --warning: #fab219;
      --critical: #d03b3b;
    }
  }
  :root[data-theme="dark"] .dash {
    color-scheme: dark;
    --surface: #12292b;
    --plane: #0a1c1e;
    --ink: #eef8f9;
    --ink-2: #acc3c5;
    --ink-muted: #839698;
    --grid: #1f3c3f;
    --baseline: #2f5559;
    --border: rgba(182,237,243,0.14);
    --chatgpt: #00a1ac;
    --chatgpt-tint: #74cbd3;
    --gemini: #cd632d;
    --gemini-tint: #f0a27f;
    --accent: #b6edf3;
    --accent-tint: #0e3c40;
    --sand: #3a332c;
    --tile-bg: #173235;
    --step-1: #7ccdd5;
    --step-2: #40b1ba;
    --step-3: #00939f;
    --step-4: #006d76;
    --good: #0ca30c;
    --warning: #fab219;
    --critical: #d03b3b;
  }

  .dash {
    background: var(--plane);
    color: var(--ink);
    font-family: "Figtree", system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 28px clamp(16px, 4vw, 48px) 56px;
    min-height: 100%;
    box-sizing: border-box;
  }
  .dash *, .dash *::before, .dash *::after { box-sizing: border-box; }
  .dash .mono { font-family: "Figtree", ui-monospace, monospace; font-variant-numeric: tabular-nums; }

  .dash-header {
    display: flex; flex-wrap: wrap; justify-content: space-between;
    align-items: flex-start; gap: 16px; max-width: 1180px; margin: 0 auto 20px;
  }
  .dash-eyebrow {
    font-size: 12px; font-weight: 600; letter-spacing: 0.08em;
    text-transform: uppercase; color: var(--accent); margin: 0 0 6px;
  }
  /* PP Editorial New is a licensed face with no webfont available here, so it
     leads the stack and falls back to a serif the reader already has. */
  .dash-title { font-family: "PP Editorial New", Georgia, "Iowan Old Style", serif;
    font-size: clamp(26px, 3.4vw, 38px); font-weight: 400; letter-spacing: -0.01em;
    margin: 0 0 6px; text-wrap: balance; }
  .dash-sub { font-size: 14px; color: var(--ink-2); margin: 0; max-width: 62ch; }
  .dash-nav { display: flex; gap: 6px; flex-wrap: wrap; }
  .dash-nav a, .dash-nav span {
    font-size: 12.5px; font-weight: 600; padding: 7px 12px; border-radius: 999px;
    border: 1px solid var(--border); color: var(--ink-2);
    text-decoration: none; white-space: nowrap;
  }
  .dash-nav .current { background: var(--accent-tint); color: var(--accent); border-color: transparent; }
  .dash-nav a:hover { border-color: var(--accent); color: var(--accent); }

  /* Reporting-period switch. Both granularities are rendered into the page,
     so this only flips which one is visible: no request, no re-render. */
  .dash-controls { display: flex; flex-direction: column; align-items: flex-end; gap: 10px; }
  .period-control { display: flex; align-items: center; gap: 9px; }
  .period-label {
    font-size: 11px; font-weight: 600; letter-spacing: 0.05em;
    text-transform: uppercase; color: var(--ink-muted); white-space: nowrap;
  }
  .period-switch {
    display: inline-flex; gap: 2px; padding: 3px; background: var(--plane);
    border: 1px solid var(--border); border-radius: 999px;
  }
  .period-switch button {
    font: 600 12.5px/1 "Figtree", system-ui, -apple-system, "Segoe UI", sans-serif;
    color: var(--ink-2); background: transparent; border: 0; cursor: pointer;
    padding: 7px 15px; border-radius: 999px;
  }
  .period-switch button:hover { color: var(--accent); }
  .period-switch button[aria-checked="true"] { background: var(--accent-tint); color: var(--accent); }
  @media (max-width: 640px) { .dash-controls { align-items: flex-start; } }

  /* A hidden period block must collapse out of the grid, not just go blank. */
  .dash [hidden] { display: none !important; }

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
    font-family: "Figtree", ui-monospace, monospace; font-variant-numeric: tabular-nums; font-size: 12px;
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

  /* Data-age readout. Hidden by default and revealed only when the page is
     being served by app.py, since a file off disk has no server to ask. */
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
  .refresh-note { font-size: 12px; color: var(--ink-muted); }

  svg.chart-svg { display: block; width: 100%; height: auto; }
  svg.chart-svg .grid-line { stroke: var(--grid); stroke-width: 1; }
  svg.chart-svg .baseline { stroke: var(--baseline); stroke-width: 1; }
  svg.chart-svg .axis-label { fill: var(--ink-muted); font-size: 10.5px; font-family: "Figtree", ui-monospace, monospace; font-variant-numeric: tabular-nums; }
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


def _period_attrs(period):
    """Tag a fragment as belonging to one reporting period.

    Both periods are rendered into the page and the switch only flips which is
    visible. Duplicating the markup costs a few KB; re-rendering it in the
    browser would mean keeping a second copy of every template in JavaScript.
    """
    hidden = "" if period == config.DEFAULT_PERIOD else " hidden"
    return f' data-period="{period}"{hidden}'


def period_span(by_period):
    """Inline text that follows the toggle. Values are plain text."""
    return "".join(
        f"<span{_period_attrs(p)}>{esc(by_period[p])}</span>" for p in config.PERIODS
    )


def period_div(by_period, cls=""):
    """Block content that follows the toggle. Values are raw HTML."""
    cls_attr = f' class="{cls}"' if cls else ""
    return "".join(
        f"<div{cls_attr}{_period_attrs(p)}>{by_period[p]}</div>" for p in config.PERIODS
    )


def chart_slots(prefix):
    """One empty chart container per period, for the page script to fill."""
    return "".join(
        f'<div id="{prefix}-{p}"{_period_attrs(p)}></div>' for p in config.PERIODS
    )


def kpi(label, value, note, unit="", headline=False, period=None):
    cls = "kpi-tile is-headline" if headline else "kpi-tile"
    unit_html = f'<span class="unit">{esc(unit)}</span>' if unit else ""
    attrs = _period_attrs(period) if period else ""
    return (
        f'<div class="{cls}"{attrs}>'
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


def delivery_lines(r):
    """The two flags, reported side by side, plus what is not being measured.

    Superseded and logged-failure are kept on separate rows on purpose. One is
    counted from rows that exist; the other is only as good as the tool's
    failure path, which currently writes nothing.
    """
    rows = [
        ("Attempts", f'{r["attempts"]:,}', "every call the tool logged"),
        ("Delivered", f'{r["delivered"]:,}', f'{r["delivered_pct"]}%'),
        ("Retried, never delivered", r["superseded"], f'{r["superseded_pct"]}%'),
        ("Failures logged by the tool", r["failed"], f'{r["failed_pct"]}%'),
    ]
    out = stat_lines(rows)
    if r["no_failure_feed"] and r["attempts"]:
        out += (
            '<p class="panel-hint" style="margin-top:10px">The tool writes a row '
            'only after a generation succeeds, so a hard API error leaves no '
            'trace and that zero is a <b>missing feed, not a clean record</b>. '
            'Retried attempts are counted from rows that do exist, which is why '
            'they can be reported.</p>'
        )
    return out


def health_pill(pct, attempts=None, good_at=95.0, warn_at=85.0):
    # Zero attempts is not a health verdict, so it gets a neutral pill rather
    # than a green one computed from an empty sample.
    if attempts == 0:
        return '<span class="pill mute">No attempts yet</span>'
    if pct >= good_at:
        return f'<span class="pill good">&#10003; Healthy &middot; {pct}% delivered</span>'
    if pct >= warn_at:
        return f'<span class="pill warn">&#9888; Degraded &middot; {pct}% delivered</span>'
    return f'<span class="pill bad">&#10007; Failing &middot; {pct}% delivered</span>'


# ============================================================
# Dashboard templates
# ============================================================
# Which dataset key each period reads. The two series carry the same row
# schema, so every chart and table below is granularity-agnostic.
SERIES_KEY = {"week": "weeks", "day": "daily"}

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


def _period_switch():
    """Segmented control. Radio semantics, because this picks one of a set of
    views rather than navigating anywhere."""
    out = ""
    for period in config.PERIODS:
        checked = "true" if period == config.DEFAULT_PERIOD else "false"
        out += (
            f'<button type="button" role="radio" data-set-period="{period}" '
            f'aria-checked="{checked}">{esc(config.PERIOD_LABELS[period])}</button>'
        )
    return (
        '<div class="period-control">'
        '<span class="period-label">Measured by</span>'
        '<div class="period-switch" role="radiogroup" aria-label="Reporting period">'
        f"{out}</div></div>"
    )


# Runs before the charts so a reader who last chose Daily does not watch the
# weekly view paint first. The chart containers are in the served markup either
# way, so building into a hidden one is fine.
PERIOD_JS = """
<script>
(function(){
  var root = document.querySelector('.dash[data-variant]');
  if (!root) return;
  var buttons = root.querySelectorAll('.period-switch button[data-set-period]');
  if (!buttons.length) return;
  var KEY = 'imagegen-dash-period';

  function apply(period) {
    // Everything downstream of the switch carries data-period. The buttons
    // use data-set-period instead, so they never hide themselves.
    var blocks = root.querySelectorAll('[data-period]');
    for (var i = 0; i < blocks.length; i++) {
      blocks[i].hidden = blocks[i].getAttribute('data-period') !== period;
    }
    for (var j = 0; j < buttons.length; j++) {
      buttons[j].setAttribute('aria-checked',
        buttons[j].getAttribute('data-set-period') === period ? 'true' : 'false');
    }
    root.setAttribute('data-period-active', period);
  }

  // The page reloads itself whenever the figures change. Without remembering
  // the choice, that reload would snap anyone reading in daily back to weekly.
  // A private window or blocked site data throws here rather than returning
  // null, so both directions are guarded.
  var initial = root.getAttribute('data-default-period') || 'week';
  try {
    var saved = window.localStorage.getItem(KEY);
    if (saved === 'week' || saved === 'day') initial = saved;
  } catch (e) {}
  apply(initial);

  for (var k = 0; k < buttons.length; k++) {
    buttons[k].addEventListener('click', function(ev){
      var p = ev.currentTarget.getAttribute('data-set-period');
      apply(p);
      try { window.localStorage.setItem(KEY, p); } catch (e) {}
    });
  }
})();
</script>
"""

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

# Auto-refresh. Only activates when app.py is serving the page: a file opened
# off disk is a static snapshot with no server to ask, so the bar stays hidden
# rather than reporting an age it cannot keep current.
#
# There is no manual control. The page polls, and the server re-reads Supabase
# whenever its cache has aged out, so the only thing a button added was reading
# through that cache a couple of minutes early. `?refresh=1` still forces a
# read for anyone who needs one from the URL.
REFRESH_JS = """
<script>
(function(){
  var root = document.querySelector('.dash[data-variant]');
  if (!root) return;
  var served = window.location.pathname.indexOf('/dashboard/') === 0;
  if (!served) return;

  var bar = root.querySelector('.refresh-bar');
  var age = root.querySelector('.refresh-age');
  if (!bar || !age) return;
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

  function check() {
    if (busy) return;
    busy = true;
    fetch('/api/status', {cache: 'no-store'})
      .then(function(r){ return r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)); })
      .then(function(s){
        bar.classList.remove('is-error');
        // Reload only when the figures actually differ, so a rebuild that
        // found nothing new does not interrupt whoever is reading.
        if (s.data_hash && s.data_hash !== pageHash) { window.location.reload(); return; }
        if (s.generated_at) generated = Date.parse(s.generated_at) || generated;
        busy = false;
        paint();
      })
      .catch(function(){
        bar.classList.add('is-error');
        busy = false;
        age.textContent = 'Could not reach the server';
      });
  }

  paint();
  setInterval(paint, 15000);
  setInterval(check, pollMs);
  document.addEventListener('visibilitychange', function(){
    if (!document.hidden) check();
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
    head = CSS.replace("__TITLE__", page_title).replace("__FAVICON__", assets.FAVICON_LINK)
    return f"""{head}
<div class="dash" data-variant="{variant}"
     data-hash="{esc(dhash)}" data-generated="{esc(generated_at)}"
     data-poll="{config.POLL_SECONDS}"
     data-default-period="{config.DEFAULT_PERIOD}">
  <div class="dash-header">
    <div>
      <p class="dash-eyebrow">{esc(eyebrow)}</p>
      <h1 class="dash-title">{esc(title)}</h1>
      <p class="dash-sub">{esc(sub)}</p>
    </div>
    <div class="dash-controls">
      <div class="dash-nav">{_nav(nav_items, variant)}</div>
      {_period_switch()}
    </div>
  </div>

  <div class="refresh-bar" hidden>
    <span class="refresh-status">
      <span class="dot"></span>
      <span class="refresh-age">Updated just now</span>
    </span>
    <span class="refresh-note">Updates itself automatically</span>
  </div>

  <div class="kpi-row">{kpis_html}</div>

  {body_html}

  <div class="dash-footer">
    <span>Live from Supabase . window {esc(window)} . generated {esc(stamp)}</span>
    <span>Refresh: python image_generation_dashboard_sync.py</span>
  </div>
</div>

{NAV_JS}
{PERIOD_JS}
{REFRESH_JS}
{CHART_JS}
{script_html}
"""


def _designer_table(dataset, scope, period):
    """scope: 'all' | 'chatgpt' | 'gemini'. period: 'week' | 'day'.

    Status is the toggle's whole point at the person level. "Returning" means
    active in 2+ distinct periods, so someone who generated on Monday and
    again on Tuesday reads as Returning on the daily view and Tried once on
    the weekly one. Both are accurate; they answer different questions, and
    early in a rollout only the daily one can answer anything at all.
    """
    plural = config.PERIOD_NOUN_PLURAL[period]
    rows, classes = [], []
    for d in dataset["designers"]:
        n = d["tool_total"] if scope == "all" else d["tool_" + scope]
        if n == 0 and not d["provisioned"]:
            continue
        # Active periods and last-used must match the column scope, otherwise
        # a Gemini-only designer reads as "not started" beside a ChatGPT date.
        active = d[f"active_{plural}_{scope}"]
        last_seen = d["last_seen_" + scope]
        if n == 0:
            status = '<span class="pill mute">Not started</span>'
        elif active >= 2:
            status = '<span class="pill good">&#10003; Returning</span>'
        else:
            status = '<span class="pill warn">&#9888; Tried once</span>'

        if scope == "all":
            cells = [esc(d["name"]), d["tool_chatgpt"], d["tool_gemini"]]
        else:
            cells = [esc(d["name"]), n]
        rows.append(cells + [active, last_seen or "Never", status])
        classes.append("is-idle" if n == 0 else "")

    lead = ["Designer", "ChatGPT", "Gemini"] if scope == "all" else ["Designer", "Actions"]
    return table(lead + ["Active " + plural, "Last used", "Status"], rows, classes)


def _designer_panel(dataset, scope, hint):
    return (
        '<div class="panel">'
        '<div class="panel-head"><p class="panel-title">By designer</p></div>'
        f'<p class="panel-hint">{hint}</p>'
        + period_div({p: _designer_table(dataset, scope, p) for p in config.PERIODS})
        + "</div>"
    )


def _period_table(dataset, variant):
    """The raw series behind the charts, at whichever granularity is showing."""
    blocks = {}
    for period in config.PERIODS:
        first = "Week of" if period == "week" else "Day"
        rows = []
        for w in dataset[SERIES_KEY[period]]:
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
            [first, "ChatGPT", "Gemini", "Active users", "Cumulative adopters", "Adoption"]
            if variant == "overall" else
            [first, "Generate", "Refine", "Total", "Active users",
             "Cumulative adopters", "Adoption"]
        )
        blocks[period] = (
            '<details class="table-toggle">'
            f"<summary>View {config.PERIOD_LABELS[period].lower()} data table</summary>"
            + table(headers, rows) + "</details>"
        )
    return '<div class="panel">' + period_div(blocks) + "</div>"


def _ms(value):
    """No samples means no time spent, so 0. Never a placeholder dash."""
    return f"{(value or 0) / 1000:.1f}s"


def render_overall(dataset, nav_items):
    # ret is keyed by period now: ret["week"] and ret["day"] answer the same
    # questions over different buckets, and every stage that depends on
    # "came back" is rendered twice, once per key.
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
        + "".join(
            kpi("Returning users", ret[p]["repeat_pct"], unit="%",
                note=(f'{ret[p]["repeat_users"]} of {ret[p]["adopters"]} came back '
                      + ("in a second week" if p == "week" else "on a second day")),
                period=p)
            for p in config.PERIODS
        )
        + kpi("Total actions", f"{total_actions:,}",
              note="generate + refine through the tool, since launch")
        + kpi("Delivered", rel["all"]["delivered_pct"], unit="%",
              note=f'{rel["all"]["unusable"]} of {rel["all"]["attempts"]} attempts '
                   f'never reached a designer')
    )

    savers = dataset["savers"]["all"]
    saver_pct = round(100 * savers / max(1, denom))

    # Only the "came back" stage moves with the period. Provisioned, adopted
    # and kept-an-output are the same people either way.
    funnel_html = period_div({p: funnel([
        ("Provisioned", denom, "designers"),
        ("Generated at least once", meta["tool_adopters"],
         f'{meta["tool_adoption_pct"]}%'),
        (f'Came back a 2nd {config.PERIOD_NOUN[p]}', ret[p]["repeat_users"],
         f'{ret[p]["repeat_pct"]}%'),
        ("Kept an output", savers, f"{saver_pct}%"),
    ]) for p in config.PERIODS})

    stickiness = period_div({p: stat_lines([
        ("Adopters", ret[p]["adopters"], f'of {denom} provisioned'),
        (f'Returning (2+ {config.PERIOD_NOUN_PLURAL[p]})', ret[p]["repeat_users"],
         f'{ret[p]["repeat_pct"]}%'),
        ("Tried once, not since", ret[p]["one_and_done"],
         f'{ret[p]["one_and_done_pct"]}%'),
        ("Never started", ret[p]["never_tried"], ""),
        (f'Avg active {config.PERIOD_NOUN_PLURAL[p]} per adopter',
         ret[p]["avg_active_periods"], ""),
    ]) for p in config.PERIODS})

    volume_title = period_span({"week": "Weekly volume by model",
                                "day": "Daily volume by model"})
    per_period = period_span({p: config.PERIOD_NOUN[p] for p in config.PERIODS})
    designer_panel = _designer_panel(
        dataset, "all",
        "Anyone provisioned but idle is listed too - that is the follow-up "
        "list for the rollout.")

    err_rows = [[esc(code), n] for code, n in rel["all"]["errors"][:6]]
    errors_html = (
        table(["Error", "Count"], err_rows) if err_rows
        else '<p class="panel-hint">No failed attempts recorded in this window.</p>'
    )
    reliability_html = (
        f'<div class="panel-head"><p class="panel-title">Reliability &amp; speed</p>'
        f'{health_pill(rel["all"]["delivered_pct"], rel["all"]["attempts"])}</div>'
        + delivery_lines(rel["all"])
        + stat_lines([
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
      <p class="panel-title">{volume_title}</p>
      <div class="panel-legend">
        <span><span class="legend-dot" style="background:var(--chatgpt)"></span>ChatGPT</span>
        <span><span class="legend-dot" style="background:var(--gemini)"></span>Gemini</span>
      </div>
    </div>
    {chart_slots("chart-volume")}
  </div>

  <div class="panel-row">
    <div class="panel">
      <div class="panel-head">
        <p class="panel-title">Active users &amp; cumulative adopters</p>
        <div class="panel-legend">
          <span><span class="legend-dot" style="background:var(--step-3)"></span>Active&nbsp;/&nbsp;{per_period}</span>
          <span><span class="legend-dot" style="background:var(--step-1)"></span>Cumulative adopters</span>
        </div>
      </div>
      {chart_slots("chart-users")}
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

  {designer_panel}

  {_period_table(dataset, "overall")}
"""

    script = """
<script>
(function(){
  // Both granularities are built up front. One set is inside a hidden block,
  // which costs nothing: an SVG sized by viewBox lays out correctly the
  // moment it is shown, and the hover handlers only fire when it is.
  const SERIES = __SERIES__;
  const root = document.querySelector('.dash[data-variant="overall"]');
  const css = k => getComputedStyle(root).getPropertyValue(k).trim();
  Object.keys(SERIES).forEach(function(period){
    window.__dashCharts.renderStackedArea(
      root.querySelector('#chart-volume-' + period), SERIES[period], [
        {key: "tool_chatgpt_total", label: "ChatGPT", color: css('--chatgpt')},
        {key: "tool_gemini_total",  label: "Gemini",  color: css('--gemini')}
      ]);
    window.__dashCharts.renderLines(
      root.querySelector('#chart-users-' + period), SERIES[period], [
        {key: "tool_active",     label: "Active / " + period,  color: css('--step-3')},
        {key: "tool_cumulative", label: "Cumulative adopters", color: css('--step-1'), dashed: true}
      ], {width: 560, height: 200});
  });
})();
</script>
""".replace("__SERIES__", json.dumps(
        {p: dataset[SERIES_KEY[p]] for p in config.PERIODS}))

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
        + kpi("Delivered", rel[variant]["delivered_pct"], unit="%",
              note=f'{rel[variant]["attempts"]:,} attempts, '
                   f'{rel[variant]["unusable"]} never reached a designer')
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

    volume_title = period_span({"week": f"Weekly {label} volume",
                                "day": f"Daily {label} volume"})
    per_period = period_span({p: config.PERIOD_NOUN[p] for p in config.PERIODS})
    designer_panel = _designer_panel(dataset, variant,
                                     f"{esc(label)} actions per designer, in the tool.")

    health_html = (
        f'<div class="panel-head"><p class="panel-title">{esc(label)} health</p>'
        f'{health_pill(rel[variant]["delivered_pct"], rel[variant]["attempts"])}</div>'
        + delivery_lines(rel[variant])
        + stat_lines([
            ("Generations delivered", f'{m["actions"]:,}',
             f'{m["generate"]} generate / {m["refine"]} refine'),
            ("Median latency", _ms(lat[variant]["p50"]), f'p95 {_ms(lat[variant]["p95"])}'),
            ("Images saved", qual[variant]["saved"], f'{qual[variant]["save_pct"]}%'),
            ("Refines per generate", qual[variant]["refines_per_generate"], ""),
        ])
    )

    body = f"""
  {empty}

  <div class="panel">
    <div class="panel-head">
      <p class="panel-title">{volume_title}</p>
      <div class="panel-legend">
        <span><span class="legend-dot" style="background:var(--{variant})"></span>Generate</span>
        <span><span class="legend-dot" style="background:var(--{variant}-tint)"></span>Refine</span>
      </div>
    </div>
    {chart_slots("chart-volume")}
  </div>

  <div class="panel-row">
    <div class="panel">
      <div class="panel-head">
        <p class="panel-title">Adopters per {per_period}</p>
        <div class="panel-legend">
          <span><span class="legend-dot" style="background:var(--{variant})"></span>Active&nbsp;/&nbsp;{per_period}</span>
          <span><span class="legend-dot" style="background:var(--{variant}-tint)"></span>Cumulative adopters</span>
        </div>
      </div>
      {chart_slots("chart-users")}
    </div>
    <div class="panel">
      <div class="panel-head"><p class="panel-title">Generate vs refine</p></div>
      <div class="share-bar">
        <div style="width:{gen_pct}%; background:var(--{variant})"></div>
        <div style="width:{ref_pct}%; background:var(--{variant}-tint)"></div>
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

  {designer_panel}

  {_period_table(dataset, variant)}
"""

    script = """
<script>
(function(){
  const SERIES = __SERIES__;
  const root = document.querySelector('.dash[data-variant="__VARIANT__"]');
  const css = k => getComputedStyle(root).getPropertyValue(k).trim();
  Object.keys(SERIES).forEach(function(period){
    window.__dashCharts.renderStackedArea(
      root.querySelector('#chart-volume-' + period), SERIES[period], [
        {key: "tool___VARIANT___generate", label: "Generate", color: css('--__VARIANT__')},
        {key: "tool___VARIANT___refine",   label: "Refine",   color: css('--__VARIANT__-tint')}
      ]);
    window.__dashCharts.renderLines(
      root.querySelector('#chart-users-' + period), SERIES[period], [
        {key: "tool___VARIANT___active",     label: "Active / " + period,  color: css('--__VARIANT__')},
        {key: "tool___VARIANT___cumulative", label: "Cumulative adopters", color: css('--__VARIANT__-tint'), dashed: true}
      ], {width: 560, height: 200});
  });
})();
</script>
""".replace("__SERIES__", json.dumps(
        {p: dataset[SERIES_KEY[p]] for p in config.PERIODS})).replace("__VARIANT__", variant)

    return _shell(variant, dataset, nav_items, kpis, body, script)


def render_html(variant, dataset, nav_items):
    if variant == "overall":
        return render_overall(dataset, nav_items)
    return render_provider(variant, dataset, nav_items)
