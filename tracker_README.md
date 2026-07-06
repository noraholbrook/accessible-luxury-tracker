# Brand discounting & health tracker (Tapestry pitch)

A self-running agent that snapshots handbag assortments every **Monday** for
**Kate Spade, Coach, Tory Burch, Michael Kors, and Marc Jacobs** (full-price and
outlet channels), stores every week, and computes the promotional-intensity /
brand-health metrics behind a "Kate Spade is recovering, discounting is down"
thesis.

## What it measures (and why it maps to the thesis)

| Metric | How it's computed | What a *bullish* move looks like |
|---|---|---|
| **% of SKUs on sale** | share of variants where `sale_price < list_price` (latest week) | ↓ falling |
| **Avg discount depth** | mean `(1 − sale/list)` over on-sale variants | ↓ shallower |
| **New arrivals sold at full price** | of variants *first seen this week*, % at full price | ↑ rising |
| **Sell-outs by style/color** | variants in-stock last week that are now OOS / delisted | ↑ faster |
| **Time-to-markdown** | median days from a style's first full-price sighting to its first markdown | ↑ longer |
| **% outlet vs full-price** | outlet variant count ÷ (outlet + full) | ↓ less outlet reliance |
| **Outlet promo?** | promo banner / “extra XX% off” / code detected on the outlet home | fewer & shallower |

The first three signal pricing power; the sell-out + time-to-markdown pair signal
demand strength; the outlet metrics signal how much the brand leans on off-price.
Track them **as a trend over weeks** — the levels matter less than the direction.

## Architecture

```
run_weekly.py         # entrypoint: scrape -> store -> compute -> report
  config.py           # per-brand URLs, method, selectors, tracked category
  fetch.py            # polite HTTP (robots.txt, rate limit, retries)
  scrape.py           # dispatch: shopify / sfcc grid / json-ld, paginate
  parse.py            # extractors + promo detector
  store.py            # SQLite: every weekly snapshot is kept
  metrics.py          # derives the 7 metrics by diffing snapshots over time
discover.py           # inspect a URL to confirm method/selectors per brand
.github/workflows/weekly.yml   # the "agent": Monday cron, commits data back
```

Why keep every snapshot? Four of the metrics (new arrivals at full price,
sell-outs, time-to-markdown) **only exist as differences between weeks**. The DB
is the memory that makes the agent's output a trend, not just a level.

## Setup

```bash
pip install -r requirements.txt
python demo_metrics.py          # sanity-check the metrics engine on synthetic data
```

### Wire each brand (do this once, ~10 min/brand)
Coach, Kate Spade, Michael Kors and Tory Burch are on **Salesforce Commerce
Cloud (Demandware/SFRA)**; Marc Jacobs is auto-detected. Markup varies by theme,
so confirm each category page before trusting numbers:

```bash
python discover.py https://www.katespade.com/shop/handbags
```
It reports whether the page is Shopify / has JSON-LD / is SFRA-grid, how many
product tiles the default selectors catch, and a sample parse. Update that
brand's `category_url` and `selectors` in `config.py` accordingly. Selectors in
config are **starting points marked TODO** — verify them.

Getting reliable `in_stock` (for sell-outs): grid pages rarely expose stock. For
accuracy, enrich the tracked styles by fetching each PDP and reading
`offers.availability` from its JSON-LD (InStock / OutOfStock). A cheaper proxy is
treating a variant's disappearance from the grid as a sell-out — noisier, since
delisting ≠ selling out (the engine labels which is which).

### Run it
```bash
python run_weekly.py            # writes reports/metrics_<Mon>.csv + summary_<Mon>.md
```

## The weekly agent + public dashboard
`.github/workflows/weekly.yml` runs `run_weekly.py` every Monday, commits the
updated `data/tracker.db` + `reports/` back to the repo (state persistence in
stateless CI), builds the dashboard with `build_site.py`, and **publishes it to
GitHub Pages** — then uploads the reports as an artifact. Push this repo and it
runs itself; no server.

**Enable the public site once:** repo **Settings -> Pages -> Build and
deployment -> Source: GitHub Actions**. Then trigger the first run from the
**Actions** tab (`Run workflow`). Your dashboard goes live at
`https://<you>.github.io/<repo>/` and refreshes every Monday. It's public — see
the caveat below.

The dashboard (`build_site.py` -> `site/index.html`) shows:
- an interactive week-over-week line chart with a metric switcher (each metric
  labelled *lower / higher is healthier*), Kate Spade emphasized;
- a "hangtag" card per brand with its latest % on sale, WoW delta, sparkline,
  outlet share, and a live-promo flag;
- the rendered weekly written read; and
- a **downloads panel**: the combined `timeseries.csv`, every weekly
  `metrics_<date>.csv`, and the raw `tracker.db` — grab whatever you want.

Preview it locally before pushing:
```bash
python seed_demo.py        # fills 6 weeks of synthetic data (delete for real use)
python build_site.py       # writes site/index.html
open site/index.html       # needs internet (Chart.js + fonts load from CDN)
```

Other scheduling options if you don't want GitHub: a cron job on any always-on
box (`0 13 * * 1`), or a scheduled job on Render/Railway/Cloud Scheduler.

Optional LLM narrative: pipe `reports/metrics_<Mon>.csv` to the Claude API to
draft the week's written read ("Kate Spade % on sale fell for the 4th straight
week…"). Keep the **scraping deterministic** (code); use the model only for the
prose — cheaper and more reliable than an LLM doing extraction.

## Important caveats
- **The Pages site is public.** Anyone with the URL can see the summary and
  download the data. That's usually fine for a pitch, but if you'd rather keep it
  private later, host the same `site/` folder on Cloudflare Pages or Netlify with
  access control, or gate the dynamic version behind auth.
- **Terms of Service / legal.** Scraping public pricing is common in equity
  research, but many sites' ToS restrict automated access. This tool defaults to
  respecting `robots.txt` and rate-limits to ~1 request / 3s. Review each site's
  ToS and robots, keep volume low, and identify your agent honestly. This isn't
  legal advice — if it's for a fund, run it past compliance. Commercial
  alternatives exist (retail price-intelligence vendors, alt-data providers) and
  are often cleaner for an investment process.
- **Data quality.** Define the universe once (same category, same country site)
  and keep it fixed, or WoW comparisons break. Made-for-outlet product is a
  *separate line*, not the full-price assortment discounted — so "outlet share"
  measures channel emphasis, not identical SKUs.
- **Sell-out inference is noisy.** Variant-level OOS flags (from PDPs) are far
  more reliable than a style vanishing from a grid (could be seasonal/regional).
- **Sanity-check against fundamentals.** Cross-read the scraped trend against
  Tapestry's reported gross margin / AUR commentary and Kate Spade comps so the
  alt-data corroborates rather than contradicts the disclosures.
- Sites change and will occasionally break the parser; `discover.py` is how you
  re-fix a brand fast.
