"""Weekly entrypoint: scrape -> store -> compute -> report.

Run manually:  python run_weekly.py
Scheduled:     GitHub Actions (.github/workflows/weekly.yml) every Monday.
"""
import os
import datetime as dt

os.chdir(os.path.dirname(os.path.abspath(__file__)))
import pandas as pd

import config, scrape, store, metrics


def monday(d=None):
    d = d or dt.date.today()
    return (d - dt.timedelta(days=d.weekday())).isoformat()


def run():
    snap = monday()
    print(f"=== Weekly run for snapshot {snap} ===")
    total = 0
    for brand, bcfg in config.BRANDS.items():
        for channel, ccfg in bcfg["channels"].items():
            print(f"[{brand}/{channel}] scraping ...")
            rows = scrape.scrape_channel(brand, channel, ccfg)
            for r in rows:
                r["snapshot_date"] = snap
            n = store.save_observations(rows)
            total += n
            print(f"    saved {n} variants")
        promo = scrape.scrape_promo(brand, bcfg)
        if promo:
            promo["snapshot_date"] = snap
            store.save_promo(promo)
            print(f"    promo: active={promo['promo_active']} "
                  f"max={promo['promo_max_pct']} :: {promo['promo_text'][:60]}")
    print(f"Total variants saved: {total}")
    build_report(snap)


def build_report(snap):
    df = store.load_observations()
    promos = store.load_promos()
    if df.empty:
        print("No data yet."); return

    table = metrics.weekly_table(df, promos, snap)
    os.makedirs("reports", exist_ok=True)
    table.to_csv(f"reports/metrics_{snap}.csv", index=False)

    # week-over-week deltas on the headline metric per brand (full channel)
    dates = sorted(df["snapshot_date"].dt.date.unique())
    lines = [f"# Discounting & brand-health tracker — {snap}\n"]
    lines.append("_Thesis check: falling % on sale + shallower depth + faster sell-outs + "
                 "more full-price newness + lower outlet reliance = brand healing / less promotional._\n")
    prev = dates[-2].isoformat() if len(dates) >= 2 else None
    for brand in sorted(df["brand"].unique()):
        cur = metrics.compute_brand_channel(df, brand, "full", snap)
        if not cur or not cur.get("n_variants"):
            continue
        delta = ""
        if prev:
            p = metrics.compute_brand_channel(df, brand, "full", prev)
            if p.get("pct_skus_on_sale") is not None:
                d = cur["pct_skus_on_sale"] - p["pct_skus_on_sale"]
                delta = f" ({d:+.1f} pts WoW)"
        os_ = metrics.outlet_share(df, brand, snap)
        lines.append(f"## {brand.replace('_', ' ').title()}")
        lines.append(f"- % of SKUs on sale: **{cur['pct_skus_on_sale']}%**{delta}")
        lines.append(f"- Avg discount depth (on-sale): **{cur['avg_discount_depth_onsale']}%**")
        lines.append(f"- New arrivals at full price: **{cur['new_arrivals_full_price_pct']}%** "
                     f"({cur['new_arrivals']} new styles)")
        lines.append(f"- Sell-out rate WoW: **{cur['sellout_rate_pct']}%** "
                     f"({cur['sellouts_count']} styles)")
        lines.append(f"- Median time-to-markdown: **{cur['time_to_markdown_median_days']} days**")
        lines.append(f"- Outlet share of assortment: **{os_['outlet_share_pct']}%**\n")
    with open(f"reports/summary_{snap}.md", "w") as f:
        f.write("\n".join(lines))
    print(f"Wrote reports/metrics_{snap}.csv and reports/summary_{snap}.md")


if __name__ == "__main__":
    run()
