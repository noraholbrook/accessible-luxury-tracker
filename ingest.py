"""Load hand-maintained weekly panel CSVs into the tracker database.

The CSVs in panel/ are the source of truth. Each weekly file is named
panel_YYYY-MM-DD.csv (the date is that Monday's snapshot). We rebuild the DB
from all of them each run, so editing a CSV and committing is all it takes.

Weekly file columns (see panel/panel_TEMPLATE.csv):
  brand, channel, product_id, variant_id, title, url,
  list_price, current_price, in_stock, is_new

Only current_price is required per row. Blank current_price -> row skipped
(not yet recorded). Blank in_stock -> assumed in stock (1). Blank is_new -> 0.
"""
import os, re, glob
import pandas as pd
import store

PANEL_GLOB = "panel/panel_*.csv"
PROMOS_FILE = "panel/promos.csv"
DATE_RE = re.compile(r"panel_(\d{4}-\d{2}-\d{2})\.csv$")


def _price(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    s = str(x).replace("$", "").replace(",", "").strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _int(x, default):
    if x is None or (isinstance(x, float) and pd.isna(x)) or str(x).strip() == "":
        return default
    try:
        return int(float(x))
    except ValueError:
        return default


def load_panels():
    rows, dates = [], set()
    for f in sorted(glob.glob(PANEL_GLOB)):
        m = DATE_RE.search(os.path.basename(f))
        if not m or "TEMPLATE" in f:
            continue
        date = m.group(1)
        df = pd.read_csv(f)
        got = 0
        for _, r in df.iterrows():
            cur = _price(r.get("current_price"))
            if cur is None:
                continue  # not filled in yet
            lst = _price(r.get("list_price")) or cur
            rows.append(dict(
                snapshot_date=date, brand=str(r["brand"]).strip(),
                channel=(str(r.get("channel", "full")).strip() or "full"),
                category="handbags", product_id=str(r["product_id"]).strip(),
                variant_id=(str(r.get("variant_id", "std")).strip() or "std"),
                title=r.get("title"), color=r.get("variant_id"), url=r.get("url"),
                list_price=lst, sale_price=cur,
                in_stock=_int(r.get("in_stock"), 1),
                is_new_flag=_int(r.get("is_new"), 0)))
            got += 1
        if got:
            dates.add(date)
        print(f"  {os.path.basename(f)}: {got} rows recorded")
    return rows, sorted(dates)


def load_promos():
    if not os.path.exists(PROMOS_FILE):
        return []
    df = pd.read_csv(PROMOS_FILE)
    out = []
    for _, r in df.iterrows():
        if pd.isna(r.get("date")):
            continue
        out.append(dict(snapshot_date=str(r["date"]).strip(), brand=str(r["brand"]).strip(),
                        channel="outlet", promo_active=_int(r.get("promo_active"), 0),
                        promo_text=("" if pd.isna(r.get("promo_text")) else str(r.get("promo_text"))),
                        promo_max_pct=None))
    return out


def rebuild():
    """Wipe and reload the DB from the CSVs (CSVs are the source of truth)."""
    if os.path.exists(store.DB_PATH):
        os.remove(store.DB_PATH)
    rows, dates = load_panels()
    if rows:
        store.save_observations(rows)
    for p in load_promos():
        store.save_promo(p)
    return rows, dates
