"""Weekly entrypoint: scrape live via ScraperAPI (if key set) + any manual
panel CSVs -> store -> compute -> report. build_site.py then publishes it.

Set SCRAPERAPI_KEY (a GitHub Actions secret) to enable live scraping.
Without it, the tracker uses only the manual panel/ CSVs.
"""
import os, datetime as dt
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.makedirs("data", exist_ok=True)
os.makedirs("reports", exist_ok=True)
os.makedirs("panel", exist_ok=True)

import config, scrape, store, metrics, ingest, fetch


def _p(v, s="%"):
    return "n/a" if v is None else f"{v}{s}"


def monday(d=None):
    d = d or dt.date.today()
    return (d - dt.timedelta(days=d.weekday())).isoformat()


def run():
    if os.path.exists(store.DB_PATH):
        os.remove(store.DB_PATH)          # rebuild fresh each run
    snap = monday()
    dates = set()

    if fetch.using_api():
        print(f"=== Live scrape via ScraperAPI (render={fetch.RENDER}) for {snap} ===")
        for brand, bcfg in config.BRANDS.items():
            for channel, ccfg in bcfg["channels"].items():
                try:
                    rows = scrape.scrape_channel(brand, channel, ccfg)
                except Exception as e:
                    print(f"  [{brand}/{channel}] error: {e}")
                    rows = []
                for r in rows:
                    r["snapshot_date"] = snap
                n = store.save_observations(rows) if rows else 0
                print(f"  [{brand}/{channel}] {n} products")
                if n:
                    dates.add(snap)
            try:
                promo = scrape.scrape_promo(brand, bcfg)
                if promo:
                    promo["snapshot_date"] = snap
                    store.save_promo(promo)
            except Exception as e:
                print(f"  [{brand}] promo error: {e}")
    else:
        print("=== No SCRAPERAPI_KEY set — using manual panel CSVs only ===")

    # merge any manually maintained panel CSVs
    csv_rows, csv_dates = ingest.load_panels()
    if csv_rows:
        store.save_observations(csv_rows)
    for pr in ingest.load_promos():
        store.save_promo(pr)
    dates |= set(csv_dates)

    if not dates:
        print("\nNo data collected. If scraping, check the per-brand counts above — "
              "0 across the board usually means the site addresses/selectors need tuning "
              "(that's the discover.py step). The dashboard will show an empty state.")
        return
    print(f"\nData for week(s): {sorted(dates)}")
    build_report(sorted(dates)[-1])


def build_report(snap):
    df = store.load_observations()
    promos = store.load_promos()
    if df.empty:
        return
    metrics.weekly_table(df, promos, snap).to_csv(f"reports/metrics_{snap}.csv", index=False)
    all_dates = sorted(df["snapshot_date"].dt.date.unique())
    prev = all_dates[-2].isoformat() if len(all_dates) >= 2 else None
    lines = [f"# Discounting & brand-health tracker — {snap}\n",
             "_Thesis check: falling % on sale + shallower depth + faster sell-outs + "
             "more full-price newness + lower outlet reliance = brand healing / less promotional._\n"]
    for brand in sorted(df["brand"].unique()):
        cur = metrics.compute_brand_channel(df, brand, "full", snap)
        if not cur or not cur.get("n_variants"):
            continue
        delta = ""
        if prev:
            p = metrics.compute_brand_channel(df, brand, "full", prev)
            if p.get("pct_skus_on_sale") is not None:
                delta = f" ({cur['pct_skus_on_sale'] - p['pct_skus_on_sale']:+.1f} pts WoW)"
        os_ = metrics.outlet_share(df, brand, snap)
        lines += [f"## {brand.replace('_', ' ').title()}",
                  f"- % of SKUs on sale: **{_p(cur['pct_skus_on_sale'])}**{delta}",
                  f"- Avg discount depth (on-sale): **{_p(cur['avg_discount_depth_onsale'])}**",
                  f"- New arrivals at full price: **{_p(cur['new_arrivals_full_price_pct'])}** "
                  f"({cur['new_arrivals'] or 0} new styles)",
                  f"- Sell-out rate WoW: **{_p(cur['sellout_rate_pct'])}** ({cur['sellouts_count'] or 0} styles)",
                  f"- Median time-to-markdown: **{_p(cur['time_to_markdown_median_days'], ' days')}**",
                  f"- Outlet share of assortment: **{_p(os_['outlet_share_pct'])}**\n"]
    open(f"reports/summary_{snap}.md", "w").write("\n".join(lines))
    print(f"Wrote reports/metrics_{snap}.csv and reports/summary_{snap}.md")


if __name__ == "__main__":
    run()
