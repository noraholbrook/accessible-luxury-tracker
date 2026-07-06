"""Derived-metrics engine.

Turns the raw weekly `observations` into the six pitch metrics. Snapshot-only
metrics (% on sale, discount depth) need just the latest week; the rest
(new arrivals at full price, sell-outs, time-to-markdown) are computed by
diffing the latest snapshot against history.

All functions take the full observations DataFrame (see store.load_observations)
so they can see history. `key` = a single variant across time.
"""
import numpy as np
import pandas as pd

EPS = 0.01  # price noise floor; treat sale within 1c of list as "not on sale"
KEYS = ["brand", "channel", "product_id", "variant_id"]


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    valid = (df["list_price"] > 0) & (df["sale_price"] > 0)
    df["on_sale"] = valid & ((df["list_price"] - df["sale_price"]) > EPS)
    df["discount_pct"] = np.where(
        valid, np.clip(1 - (df["sale_price"] / df["list_price"]), 0, None), 0.0
    )
    return df


def _snapshot_dates(df):
    return sorted(df["snapshot_date"].dropna().unique())


def compute_brand_channel(df, brand, channel, as_of=None) -> dict:
    """All metrics for one brand+channel as of a snapshot date (default: latest)."""
    df = _prep(df)
    dates = _snapshot_dates(df)
    if not dates:
        return {}
    as_of = pd.to_datetime(as_of) if as_of is not None else dates[-1]
    prev = max([d for d in dates if d < as_of], default=None)

    scope = df[(df.brand == brand) & (df.channel == channel)]
    cur = scope[scope.snapshot_date == as_of]
    out = {"brand": brand, "channel": channel, "as_of": str(pd.Timestamp(as_of).date()),
           "n_variants": int(len(cur)), "n_styles": int(cur["product_id"].nunique())}
    if cur.empty:
        return out

    # --- snapshot metrics ---
    out["pct_skus_on_sale"] = round(100 * cur["on_sale"].mean(), 1)
    out["avg_discount_depth_all"] = round(100 * cur["discount_pct"].mean(), 1)
    onsale = cur[cur.on_sale]
    out["avg_discount_depth_onsale"] = round(100 * onsale["discount_pct"].mean(), 1) if len(onsale) else 0.0

    # first-seen per variant across ALL history (for new-arrival + time-to-markdown)
    first_seen = scope.groupby(KEYS)["snapshot_date"].min()

    # --- new arrivals sold at full price ---
    if prev is not None:
        cur_keyed = cur.set_index(KEYS)
        new_keys = [k for k in cur_keyed.index if first_seen.loc[k] == as_of]
        if new_keys:
            new_rows = cur_keyed.loc[new_keys]
            out["new_arrivals"] = int(len(new_rows))
            out["new_arrivals_full_price_pct"] = round(100 * (~new_rows["on_sale"]).mean(), 1)
        else:
            out["new_arrivals"] = 0
            out["new_arrivals_full_price_pct"] = None
    else:
        out["new_arrivals"] = None
        out["new_arrivals_full_price_pct"] = None  # first run: everything is "new"

    # --- sell-outs by style/color (vs previous snapshot) ---
    if prev is not None:
        prev_rows = scope[(scope.snapshot_date == prev)].set_index(KEYS)
        was_instock = prev_rows[prev_rows["in_stock"] == 1]
        cur_idx = cur.set_index(KEYS)
        sold_out = []
        for k in was_instock.index:
            if k not in cur_idx.index:
                status = "delisted"
            elif cur_idx.loc[[k]]["in_stock"].iloc[0] == 0:
                status = "out_of_stock"
            else:
                continue
            r = was_instock.loc[[k]].iloc[0]
            sold_out.append({"product_id": k[2], "variant_id": k[3],
                             "title": r.get("title"), "color": r.get("color"),
                             "status": status})
        base = max(len(was_instock), 1)
        out["sellouts_count"] = len(sold_out)
        out["sellout_rate_pct"] = round(100 * len(sold_out) / base, 1)
        out["sellouts_detail"] = sold_out
    else:
        out["sellouts_count"] = None
        out["sellout_rate_pct"] = None
        out["sellouts_detail"] = []

    # --- time-to-markdown (days from first full-price sighting to first markdown) ---
    # Only variants whose FIRST observation was full price (clean clock).
    ttm_days = []
    still_full = 0
    for k, g in scope.sort_values("snapshot_date").groupby(KEYS):
        if g.iloc[0]["on_sale"]:
            continue  # left-censored: already discounted when first seen
        md = g[g["on_sale"]]
        if len(md):
            days = (md.iloc[0]["snapshot_date"] - g.iloc[0]["snapshot_date"]).days
            ttm_days.append(days)
        else:
            still_full += 1
    out["time_to_markdown_median_days"] = float(np.median(ttm_days)) if ttm_days else None
    out["n_marked_down"] = len(ttm_days)
    out["n_still_full_price"] = still_full  # right-censored (never marked down yet)
    return out


def outlet_share(df, brand, as_of=None) -> dict:
    """% of tracked assortment that is outlet vs full-price for a brand."""
    dates = _snapshot_dates(df)
    if not dates:
        return {}
    as_of = pd.to_datetime(as_of) if as_of is not None else dates[-1]
    cur = df[(df.brand == brand) & (df.snapshot_date == as_of)]
    n_full = int((cur.channel == "full").sum())
    n_out = int((cur.channel == "outlet").sum())
    total = n_full + n_out
    return {"brand": brand, "as_of": str(pd.Timestamp(as_of).date()),
            "n_full": n_full, "n_outlet": n_out,
            "outlet_share_pct": round(100 * n_out / total, 1) if total else None}


def weekly_table(df, promos=None, as_of=None) -> pd.DataFrame:
    """One tidy row per brand+channel; the thing you chart week over week."""
    rows = []
    for brand in sorted(df["brand"].unique()):
        for channel in sorted(df[df.brand == brand]["channel"].unique()):
            m = compute_brand_channel(df, brand, channel, as_of)
            m.pop("sellouts_detail", None)
            os_ = outlet_share(df, brand, as_of)
            m["outlet_share_pct"] = os_.get("outlet_share_pct")
            if promos is not None and not promos.empty:
                p = promos[(promos.brand == brand) & (promos.channel == channel)]
                if as_of is not None:
                    p = p[p.snapshot_date == pd.to_datetime(as_of)]
                if len(p):
                    m["outlet_promo"] = bool(p.iloc[-1]["promo_active"])
                    m["outlet_promo_text"] = p.iloc[-1]["promo_text"]
            rows.append(m)
    return pd.DataFrame(rows)
