"""Build a static, self-updating dashboard from the tracker DB.

Produces site/:
  index.html            charted dashboard (Chart.js) with embedded time series
  data/timeseries.csv   one tidy row per brand/channel/week (combined)
  data/metrics_*.csv     each weekly snapshot (copied from reports/)
  data/tracker.db        the raw SQLite database
  .nojekyll             so GitHub Pages serves files as-is

Run after run_weekly.py. The weekly GitHub Action calls this and deploys site/.
"""
import os, json, shutil, glob, sqlite3, datetime as dt

os.chdir(os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import store, metrics

SITE = "site"
DATA = os.path.join(SITE, "data")

# metric -> (label, unit, healthier_direction)  down = lower is healthier
METRICS = [
    ("pct_skus_on_sale",             "% of SKUs on sale",        "%",    "down"),
    ("avg_discount_depth_onsale",    "Avg discount depth",       "%",    "down"),
    ("new_arrivals_full_price_pct",  "New arrivals at full price","%",   "up"),
    ("sellout_rate_pct",             "Sell-out rate (WoW)",      "%",    "up"),
    ("time_to_markdown_median_days", "Time-to-markdown",         " days","up"),
    ("outlet_share_pct",             "Outlet share of assortment","%",   "down"),
]
BRAND_COLORS = {
    "kate_spade": "#C0523A", "coach": "#14776A", "michael_kors": "#3A5A78",
    "tory_burch": "#B5762A", "marc_jacobs": "#6B5B95",
}
def nice(b): return b.replace("_", " ").title()


def build_timeseries(df, promos):
    dates = sorted(pd.to_datetime(df["snapshot_date"]).dt.date.unique())
    date_strs = [d.isoformat() for d in dates]
    brands = sorted(df["brand"].unique())
    series = {b: {m[0]: [] for m in METRICS} for b in brands}
    for b in brands:
        series[b]["promo"] = []
    tidy_rows = []
    for d in dates:
        wt = metrics.weekly_table(df, promos, d.isoformat())
        for b in brands:
            row_full = wt[(wt.brand == b) & (wt.channel == "full")]
            r = row_full.iloc[0].to_dict() if len(row_full) else {}
            for key, *_ in METRICS:
                v = r.get(key)
                series[b][key].append(None if pd.isna(v) else round(float(v), 1) if v is not None else None)
            promo_any = bool(wt[(wt.brand == b)]["outlet_promo"].fillna(False).any()) if "outlet_promo" in wt else False
            series[b]["promo"].append(promo_any)
            tidy = {"date": d.isoformat(), "brand": b}
            tidy.update({k: r.get(k) for k, *_ in METRICS})
            tidy["outlet_promo"] = promo_any
            tidy_rows.append(tidy)
    return date_strs, brands, series, pd.DataFrame(tidy_rows)


def sparkline_svg(vals, color, w=132, h=34, pad=3):
    pts = [(i, v) for i, v in enumerate(vals) if v is not None]
    if len(pts) < 2:
        return f'<svg viewBox="0 0 {w} {h}" class="spark"></svg>'
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    xmin, xmax = min(xs), max(xs); ymin, ymax = min(ys), max(ys)
    yr = (ymax - ymin) or 1; xr = (xmax - xmin) or 1
    def X(x): return pad + (x - xmin) / xr * (w - 2 * pad)
    def Y(y): return h - pad - (y - ymin) / yr * (h - 2 * pad)
    d = "M" + " L".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in pts)
    cx, cy = X(xs[-1]), Y(ys[-1])
    return (f'<svg viewBox="0 0 {w} {h}" class="spark" preserveAspectRatio="none">'
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="2.6" fill="{color}"/></svg>')


def delta_badge(vals, direction):
    v = [x for x in vals if x is not None]
    if len(v) < 2:
        return '<span class="delta flat">—</span>'
    d = v[-1] - v[-2]
    if abs(d) < 0.05:
        return '<span class="delta flat">±0.0</span>'
    healthier = (d < 0 and direction == "down") or (d > 0 and direction == "up")
    arrow = "▼" if d < 0 else "▲"
    cls = "good" if healthier else "bad"
    return f'<span class="delta {cls}">{arrow} {abs(d):.1f}</span>'


def md_to_html(md):
    out, in_ul = [], False
    for line in md.splitlines():
        s = line.rstrip()
        if s.startswith("## "):
            if in_ul: out.append("</ul>"); in_ul = False
            out.append(f"<h3>{_ib(s[3:])}</h3>")
        elif s.startswith("# "):
            if in_ul: out.append("</ul>"); in_ul = False
            out.append(f"<h2>{_ib(s[2:])}</h2>")
        elif s.startswith("- "):
            if not in_ul: out.append("<ul>"); in_ul = True
            out.append(f"<li>{_ib(s[2:])}</li>")
        elif s.startswith("_") and s.endswith("_") and len(s) > 2:
            if in_ul: out.append("</ul>"); in_ul = False
            out.append(f'<p class="note">{_ib(s.strip("_"))}</p>')
        elif s:
            if in_ul: out.append("</ul>"); in_ul = False
            out.append(f"<p>{_ib(s)}</p>")
    if in_ul: out.append("</ul>")
    return "\n".join(out)

def _ib(t):
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)


def build():
    df = store.load_observations()
    promos = store.load_promos()
    os.makedirs(DATA, exist_ok=True)
    if df.empty:
        print("No data yet — run run_weekly.py first."); return

    dates, brands, series, tidy = build_timeseries(df, promos)
    latest = dates[-1]

    # --- copy downloadable data ---
    tidy.to_csv(os.path.join(DATA, "timeseries.csv"), index=False)
    for csv in glob.glob("reports/metrics_*.csv") + glob.glob("reports/SAMPLE_metrics.csv"):
        shutil.copy(csv, DATA)
    if os.path.exists("data/tracker.db"):
        shutil.copy("data/tracker.db", os.path.join(DATA, "tracker.db"))
    downloads = sorted(os.listdir(DATA))

    # --- latest written summary ---
    summ = sorted(glob.glob("reports/summary_*.md")) + glob.glob("reports/SAMPLE_summary.md")
    summary_html = md_to_html(open(summ[-1]).read()) if summ else "<p class='note'>No summary yet.</p>"

    # --- brand hangtag cards ---
    cards = []
    for b in brands:
        color = BRAND_COLORS.get(b, "#333")
        on_sale = series[b]["pct_skus_on_sale"]
        latest_v = next((x for x in reversed(on_sale) if x is not None), None)
        promo_on = series[b]["promo"][-1] if series[b]["promo"] else False
        outlet = next((x for x in reversed(series[b]["outlet_share_pct"]) if x is not None), None)
        cards.append(f"""
      <article class="tag" style="--brand:{color}">
        <span class="tag-hole"></span>
        <header><h3>{nice(b)}</h3>{delta_badge(on_sale,'down')}</header>
        <div class="tag-stat"><span class="big">{'' if latest_v is None else f'{latest_v:.0f}'}<span class="pct">%</span></span>
          <span class="tag-label">on sale</span></div>
        {sparkline_svg(on_sale, color)}
        <footer><span>Outlet {('—' if outlet is None else f'{outlet:.0f}%')}</span>
          <span class="promo {'on' if promo_on else 'off'}">{'PROMO LIVE' if promo_on else 'no promo'}</span></footer>
      </article>""")

    payload = {
        "dates": dates,
        "series": series,
        "brandColors": BRAND_COLORS,
        "brandNames": {b: nice(b) for b in brands},
        "metrics": [{"key": k, "label": l, "unit": u, "dir": d} for k, l, u, d in METRICS],
    }

    html = (TEMPLATE
            .replace("__LATEST__", latest)
            .replace("__NWEEKS__", str(len(dates)))
            .replace("__NBRANDS__", str(len(brands)))
            .replace("__CARDS__", "\n".join(cards))
            .replace("__SUMMARY__", summary_html)
            .replace("__DOWNLOADS__", "\n".join(
                f'<li><a href="./data/{f}" download>{f}</a> '
                f'<span class="sz">{os.path.getsize(os.path.join(DATA,f))//1024 or 1} KB</span></li>'
                for f in downloads))
            .replace("__PAYLOAD__", json.dumps(payload)))

    with open(os.path.join(SITE, "index.html"), "w") as f:
        f.write(html)
    open(os.path.join(SITE, ".nojekyll"), "w").close()
    print(f"Built {SITE}/index.html  ({len(dates)} weeks, {len(brands)} brands)")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Competitive Pricing Monitor</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root{
  --ink:#14181A; --paper:#EAEDEB; --panel:#FFFFFF; --muted:#5F6B66;
  --rule:#D5DAD7; --signal:#14776A; --markdown:#C0523A; --shadow:0 1px 2px rgba(20,24,26,.06);
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:"IBM Plex Sans",system-ui,sans-serif;line-height:1.5;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:1160px;margin:0 auto;padding:0 24px}
.num{font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums}
a{color:var(--signal)}

/* masthead */
header.top{border-bottom:1px solid var(--ink);padding:34px 0 22px;margin-bottom:30px}
.eyebrow{font-family:"IBM Plex Mono",monospace;font-size:12px;letter-spacing:.22em;
  text-transform:uppercase;color:var(--markdown);font-weight:500}
h1{font-family:"Space Grotesk",sans-serif;font-weight:700;font-size:clamp(30px,4.2vw,52px);
  line-height:1.02;margin:.28em 0 .3em;letter-spacing:-.01em}
.sub{max-width:60ch;color:var(--muted);font-size:15px}
.meta{margin-top:16px;display:flex;gap:26px;flex-wrap:wrap;font-family:"IBM Plex Mono",monospace;
  font-size:12.5px;color:var(--muted)}
.meta b{color:var(--ink);font-weight:500}

section{margin-bottom:38px}
.label{font-family:"IBM Plex Mono",monospace;font-size:11.5px;letter-spacing:.18em;
  text-transform:uppercase;color:var(--muted);margin:0 0 14px}

/* controls */
.controls{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:flex-end;margin-bottom:14px}
.seg{display:inline-flex;flex-wrap:wrap;border:1px solid var(--rule);border-radius:9px;overflow:hidden;background:var(--panel)}
.seg button{font-family:inherit;font-size:12.5px;padding:8px 13px;border:0;background:transparent;
  color:var(--muted);cursor:pointer;border-right:1px solid var(--rule)}
.seg button:last-child{border-right:0}
.seg button[aria-pressed=true]{background:var(--ink);color:#fff}
.dirhint{font-family:"IBM Plex Mono",monospace;font-size:12px;color:var(--muted)}
.dirhint b{color:var(--signal)}

.panel{background:var(--panel);border:1px solid var(--rule);border-radius:14px;
  padding:18px 18px 10px;box-shadow:var(--shadow)}
.chartbox{position:relative;height:360px}
.legend{display:flex;gap:14px;flex-wrap:wrap;margin:12px 2px 4px}
.legend button{font-family:inherit;font-size:12.5px;display:inline-flex;align-items:center;gap:7px;
  background:none;border:0;cursor:pointer;color:var(--ink);opacity:.4;padding:2px}
.legend button.on{opacity:1}
.dot{width:11px;height:11px;border-radius:50%}

/* hangtag brand cards — the signature */
.tags{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:16px}
.tag{position:relative;background:var(--panel);border:1px solid var(--rule);
  border-radius:10px 10px 10px 10px;padding:16px 16px 12px;box-shadow:var(--shadow);
  border-top:3px solid var(--brand)}
.tag::before{content:"";position:absolute;top:-3px;left:26px;width:34px;height:3px;background:var(--brand)}
.tag-hole{position:absolute;top:12px;right:14px;width:11px;height:11px;border-radius:50%;
  border:1.5px solid var(--rule);background:var(--paper)}
.tag header{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.tag h3{font-family:"Space Grotesk",sans-serif;font-size:15px;margin:0;font-weight:500}
.tag-stat{display:flex;align-items:baseline;gap:8px;margin-bottom:4px}
.big{font-family:"Space Grotesk",sans-serif;font-size:38px;font-weight:700;line-height:1}
.big .pct{font-size:17px;color:var(--muted);margin-left:1px}
.tag-label{font-size:12px;color:var(--muted)}
.spark{width:100%;height:34px;display:block;margin:2px 0 8px}
.tag footer{display:flex;justify-content:space-between;font-family:"IBM Plex Mono",monospace;
  font-size:11px;color:var(--muted);border-top:1px solid var(--rule);padding-top:8px}
.promo.on{color:var(--markdown);font-weight:500}
.delta{font-family:"IBM Plex Mono",monospace;font-size:12px;font-weight:500;margin-left:auto}
.delta.good{color:var(--signal)} .delta.bad{color:var(--markdown)} .delta.flat{color:var(--muted)}

/* summary + downloads */
.grid2{display:grid;grid-template-columns:1.6fr 1fr;gap:24px;align-items:start}
.read h2{font-family:"Space Grotesk",sans-serif;font-size:19px;margin:.2em 0 .5em}
.read h3{font-family:"Space Grotesk",sans-serif;font-size:15px;margin:1.1em 0 .3em}
.read .note{color:var(--muted);font-size:13.5px;font-style:italic}
.read ul{margin:.2em 0 1em;padding-left:1.1em}
.read li{margin:.28em 0;font-size:14px}
.read strong{font-family:"IBM Plex Mono",monospace;font-weight:500}
.dl{background:var(--panel);border:1px solid var(--rule);border-radius:14px;padding:18px;box-shadow:var(--shadow)}
.dl ul{list-style:none;margin:0;padding:0}
.dl li{display:flex;justify-content:space-between;gap:10px;padding:8px 0;border-bottom:1px solid var(--rule);font-size:13.5px}
.dl li:last-child{border-bottom:0}
.dl a{font-family:"IBM Plex Mono",monospace;word-break:break-all}
.sz{color:var(--muted);font-family:"IBM Plex Mono",monospace;font-size:12px;white-space:nowrap}

footer.foot{border-top:1px solid var(--ink);margin-top:40px;padding:20px 0 60px;color:var(--muted);font-size:12.5px}
@media(max-width:820px){.grid2{grid-template-columns:1fr}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div class="eyebrow">Competitive Pricing Monitor · Tapestry &amp; peers</div>
    <h1>Is the discounting coming down?</h1>
    <p class="sub">A weekly read on promotional intensity and brand health across handbag
    assortments — the falling-markdown, faster-sell-out signal behind the Kate&nbsp;Spade
    recovery thesis. Lower sale penetration, shallower depth and less outlet reliance read
    as a brand pricing with confidence.</p>
    <div class="meta"><span>Latest snapshot <b>__LATEST__</b></span>
      <span>Weeks tracked <b class="num">__NWEEKS__</b></span>
      <span>Brands <b class="num">__NBRANDS__</b></span></div>
  </header>

  <section>
    <div class="controls">
      <div class="seg" id="metricSeg" role="group" aria-label="Metric"></div>
      <div class="dirhint" id="dirHint"></div>
    </div>
    <div class="panel">
      <div class="chartbox"><canvas id="main"></canvas></div>
      <div class="legend" id="legend"></div>
    </div>
  </section>

  <section>
    <p class="label">By brand · % of SKUs on sale, latest week &amp; trend</p>
    <div class="tags">__CARDS__</div>
  </section>

  <section class="grid2">
    <div class="read">
      <p class="label">This week's read</p>
      __SUMMARY__
    </div>
    <div>
      <p class="label">Download supporting data</p>
      <div class="dl"><ul>__DOWNLOADS__</ul></div>
    </div>
  </section>

  <footer class="foot">
    Illustrative until per-brand scrapers are verified (see repo README). Metrics derived from
    weekly public catalog snapshots; sell-outs/time-to-markdown are week-over-week inferences.
    Respect each site's Terms of Service. Not investment advice.
  </footer>
</div>

<script>
const DATA = __PAYLOAD__;
const brands = Object.keys(DATA.series);
const hidden = new Set();
let metric = DATA.metrics[0];

const ctx = document.getElementById('main');
let chart;

function datasets(){
  return brands.filter(b=>!hidden.has(b)).map(b=>({
    label: DATA.brandNames[b],
    data: DATA.series[b][metric.key],
    borderColor: DATA.brandColors[b],
    backgroundColor: DATA.brandColors[b],
    borderWidth: b==='kate_spade'?3:1.8,
    pointRadius: 2.5, pointHoverRadius:5, tension:.28, spanGaps:true
  }));
}
function render(){
  const cfg={type:'line',data:{labels:DATA.dates,datasets:datasets()},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      scales:{y:{ticks:{callback:v=>v+metric.unit,font:{family:'IBM Plex Mono'}},grid:{color:'#E7EAE8'}},
              x:{grid:{display:false},ticks:{font:{family:'IBM Plex Mono',size:11}}}},
      plugins:{legend:{display:false},
        tooltip:{callbacks:{label:c=>` ${c.dataset.label}: ${c.parsed.y}${metric.unit}`}}}}};
  if(chart) chart.destroy();
  chart=new Chart(ctx,cfg);
}
function buildSeg(){
  const seg=document.getElementById('metricSeg');
  DATA.metrics.forEach((m,i)=>{
    const b=document.createElement('button');
    b.textContent=m.label; b.setAttribute('aria-pressed', i===0);
    b.onclick=()=>{metric=m;[...seg.children].forEach(c=>c.setAttribute('aria-pressed',c===b));updateHint();render();};
    seg.appendChild(b);
  });
}
function updateHint(){
  const good = metric.dir==='down' ? 'lower is healthier' : 'higher is healthier';
  document.getElementById('dirHint').innerHTML = (metric.dir==='down'?'▼ ':'▲ ')+'<b>'+good+'</b>';
}
function buildLegend(){
  const el=document.getElementById('legend');
  brands.forEach(b=>{
    const btn=document.createElement('button');btn.className='on';
    btn.innerHTML=`<span class="dot" style="background:${DATA.brandColors[b]}"></span>${DATA.brandNames[b]}`;
    btn.onclick=()=>{hidden.has(b)?hidden.delete(b):hidden.add(b);btn.classList.toggle('on');render();};
    el.appendChild(btn);
  });
}
buildSeg();buildLegend();updateHint();render();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    build()
