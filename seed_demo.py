"""Seed 6 weeks of synthetic data across all 5 brands to exercise the dashboard.
Kate Spade shows the 'discounting coming down' trend; others are steadier.
Replace with real scraped data by running run_weekly.py for real.
"""
import os, random, datetime as dt
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import store, run_weekly
random.seed(7)

if os.path.exists("data/tracker.db"): os.remove("data/tracker.db")
for f in list(__import__("glob").glob("reports/metrics_*.csv")) + list(__import__("glob").glob("reports/summary_*.md")):
    os.remove(f)

WEEKS = [(dt.date(2026, 5, 25) + dt.timedelta(weeks=w)).isoformat() for w in range(6)]
COLORS = ["black", "cream", "pink", "navy", "red", "tan", "green", "blue"]

# per-brand trajectory: (on_sale_start->end, depth_start->end, sellout, outlet_n_start->end)
BRANDS = {
    "kate_spade":   dict(sale=(0.55, 0.30), depth=(0.46, 0.33), sell=(0.05, 0.14), outlet=(34, 20)),
    "coach":        dict(sale=(0.28, 0.24), depth=(0.34, 0.31), sell=(0.06, 0.08), outlet=(40, 38)),
    "michael_kors": dict(sale=(0.62, 0.60), depth=(0.44, 0.45), sell=(0.04, 0.05), outlet=(55, 55)),
    "tory_burch":   dict(sale=(0.33, 0.30), depth=(0.38, 0.36), sell=(0.05, 0.06), outlet=(22, 21)),
    "marc_jacobs":  dict(sale=(0.40, 0.37), depth=(0.42, 0.41), sell=(0.05, 0.06), outlet=(18, 17)),
}
BASE_N = 40

def lerp(a, b, t): return a + (b - a) * t

for brand, p in BRANDS.items():
    base = [(f"{brand}-s{i:02d}", random.choice(COLORS), random.choice([298, 348, 398, 448, 498]))
            for i in range(BASE_N)]
    new_pool = []  # accumulates new arrivals so they persist
    for wi, week in enumerate(WEEKS):
        t = wi / (len(WEEKS) - 1)
        sale_rate = lerp(*p["sale"], t) if False else lerp(p["sale"][0], p["sale"][1], t)
        depth = lerp(p["depth"][0], p["depth"][1], t)
        sell = lerp(p["sell"][0], p["sell"][1], t)
        outlet_n = int(round(lerp(p["outlet"][0], p["outlet"][1], t)))

        skus = base + new_pool
        n_sale = int(round(sale_rate * len(skus)))
        on_sale_idx = set(random.sample(range(len(skus)), n_sale))
        rows = []
        for i, (pid, color, listp) in enumerate(skus):
            if i in on_sale_idx:
                sp = round(listp * (1 - depth * random.uniform(.85, 1.15)))
            else:
                sp = listp
            instock = 0 if random.random() < sell else 1
            rows.append(dict(snapshot_date=week, brand=brand, channel="full", category="handbags",
                             product_id=pid, variant_id=color, title=f"{brand} bag {pid[-3:]}",
                             color=color, url="http://x", list_price=listp, sale_price=sp,
                             in_stock=instock, is_new_flag=0))
        # new arrivals this week (full price, tagged new) — supports "full-price newness"
        for k in range(3):
            pid = f"{brand}-n{wi}{k}"; color = random.choice(COLORS); listp = random.choice([398, 448, 498])
            new_pool.append((pid, color, listp))
            rows.append(dict(snapshot_date=week, brand=brand, channel="full", category="handbags",
                             product_id=pid, variant_id=color, title=f"{brand} new {pid[-2:]}",
                             color=color, url="http://x", list_price=listp, sale_price=listp,
                             in_stock=1, is_new_flag=1))
        # outlet channel rows (all discounted) to drive outlet share
        for j in range(outlet_n):
            listp = random.choice([200, 250, 300, 350])
            rows.append(dict(snapshot_date=week, brand=brand, channel="outlet", category="handbags",
                             product_id=f"{brand}-o{j:02d}", variant_id=random.choice(COLORS),
                             title=f"{brand} outlet {j}", color=random.choice(COLORS), url="http://x",
                             list_price=listp, sale_price=round(listp * 0.6), in_stock=1, is_new_flag=0))
        store.save_observations(rows)
        # outlet promo: KS drops its promo in later weeks (thesis); MK always promoting
        promo_on = (brand == "michael_kors") or (brand == "kate_spade" and wi < 3) or (brand == "coach" and wi % 2 == 0)
        store.save_promo(dict(snapshot_date=week, brand=brand, channel="outlet",
                              promo_active=1 if promo_on else 0,
                              promo_text="Extra 30% off sitewide, code SAVE30" if promo_on else "",
                              promo_max_pct=30.0 if promo_on else None))

# build weekly reports for every week (gives per-week CSVs for download + latest summary)
for week in WEEKS:
    run_weekly.build_report(week)
print("Seeded", len(WEEKS), "weeks for", len(BRANDS), "brands.")
