"""Validates the metrics engine on synthetic data (no scraping)."""
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import store, metrics

# 3 Mondays
W1, W2, W3 = "2026-06-15", "2026-06-22", "2026-06-29"

def obs(date, pid, color, listp, salep, instock, new=0, brand="kate_spade", channel="full"):
    return dict(snapshot_date=date, brand=brand, channel=channel, category="handbags",
                product_id=pid, variant_id=color, title=f"{pid} bag", color=color,
                url="http://x", list_price=listp, sale_price=salep, in_stock=instock, is_new_flag=new)

rows = []
# A: full price all 3 weeks (never marked down -> right-censored)
for d in (W1, W2, W3): rows.append(obs(d, "A", "black", 398, 398, 1))
# B: full wk1, marked down wk2 & wk3 (ttm = 7 days)
rows += [obs(W1,"B","pink",448,448,1), obs(W2,"B","pink",448,358,1), obs(W3,"B","pink",448,358,1)]
# C: full & in stock wk1-2, SOLD OUT wk3
rows += [obs(W1,"C","blue",298,298,1), obs(W2,"C","blue",298,298,1), obs(W3,"C","blue",298,298,0)]
# D: NEW arrival wk2 at full price
rows += [obs(W2,"D","red",498,498,1,new=1), obs(W3,"D","red",498,498,1)]
# E: NEW arrival wk3 already on sale
rows += [obs(W3,"E","green",500,250,1,new=1)]
# outlet channel rows (to test outlet share): 4 outlet SKUs in wk3
for i,c in enumerate(["tan","navy","ivory","olive"]):
    rows.append(obs(W3, f"O{i}", c, 300, 179, 1, channel="outlet"))

if os.path.exists("data/tracker.db"): os.remove("data/tracker.db")
store.save_observations(rows)
store.save_promo(dict(snapshot_date=W3, brand="kate_spade", channel="outlet",
                      promo_active=1, promo_text="Extra 40% off sitewide, code SAVE40", promo_max_pct=40.0))

df = store.load_observations()
promos = store.load_promos()

print("=== Kate Spade / full, as of", W3, "===")
m = metrics.compute_brand_channel(df, "kate_spade", "full", W3)
for k in ["n_variants","pct_skus_on_sale","avg_discount_depth_onsale","new_arrivals",
          "new_arrivals_full_price_pct","sellouts_count","sellout_rate_pct",
          "time_to_markdown_median_days","n_still_full_price"]:
    print(f"  {k:32s}: {m[k]}")
print("  sellouts_detail:", m["sellouts_detail"])
print("  outlet_share:", metrics.outlet_share(df, "kate_spade", W3))
print("\n=== weekly_table ===")
import pandas as pd; pd.set_option("display.width",160); pd.set_option("display.max_columns",30)
print(metrics.weekly_table(df, promos, W3)[
    ["brand","channel","n_variants","pct_skus_on_sale","avg_discount_depth_onsale",
     "new_arrivals_full_price_pct","sellout_rate_pct","time_to_markdown_median_days",
     "outlet_share_pct","outlet_promo" if "outlet_promo" else "brand"]].to_string(index=False))
