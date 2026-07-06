"""SQLite storage for weekly product observations and outlet promos.

One row in `observations` = one variant (style x color) seen in one weekly
snapshot. Sell-outs, time-to-markdown and new-arrival metrics are all derived
by comparing snapshots over time, so we keep every week's raw rows.
"""
import sqlite3
from contextlib import contextmanager
import pandas as pd

DB_PATH = "data/tracker.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    snapshot_date TEXT NOT NULL,      -- ISO date of the Monday run
    brand         TEXT NOT NULL,
    channel       TEXT NOT NULL,      -- 'full' or 'outlet'
    category      TEXT NOT NULL,      -- e.g. 'handbags'
    product_id    TEXT NOT NULL,      -- stable style id from the site
    variant_id    TEXT NOT NULL,      -- color (and size, if relevant)
    title         TEXT,
    color         TEXT,
    url           TEXT,
    list_price    REAL,              -- original / compare-at price
    sale_price    REAL,              -- current price
    in_stock      INTEGER,           -- 1 / 0 / NULL(unknown)
    is_new_flag   INTEGER,           -- 1 if site tags it "new", else 0 / NULL
    PRIMARY KEY (snapshot_date, brand, channel, product_id, variant_id)
);

CREATE TABLE IF NOT EXISTS promos (
    snapshot_date TEXT NOT NULL,
    brand         TEXT NOT NULL,
    channel       TEXT NOT NULL,
    promo_active  INTEGER,
    promo_text    TEXT,
    promo_max_pct REAL,               -- largest % off mentioned, if any
    PRIMARY KEY (snapshot_date, brand, channel)
);
"""


@contextmanager
def _conn(db_path=DB_PATH):
    con = sqlite3.connect(db_path)
    try:
        con.executescript(SCHEMA)
        yield con
        con.commit()
    finally:
        con.close()


def save_observations(rows, db_path=DB_PATH):
    """rows: list of dicts matching the observations columns."""
    cols = ["snapshot_date", "brand", "channel", "category", "product_id",
            "variant_id", "title", "color", "url", "list_price", "sale_price",
            "in_stock", "is_new_flag"]
    with _conn(db_path) as con:
        con.executemany(
            f"INSERT OR REPLACE INTO observations ({','.join(cols)}) "
            f"VALUES ({','.join('?' * len(cols))})",
            [tuple(r.get(c) for c in cols) for r in rows],
        )
    return len(rows)


def save_promo(row, db_path=DB_PATH):
    cols = ["snapshot_date", "brand", "channel", "promo_active", "promo_text", "promo_max_pct"]
    with _conn(db_path) as con:
        con.execute(
            f"INSERT OR REPLACE INTO promos ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
            tuple(row.get(c) for c in cols),
        )


def load_observations(db_path=DB_PATH) -> pd.DataFrame:
    with _conn(db_path) as con:
        df = pd.read_sql_query("SELECT * FROM observations", con)
    if not df.empty:
        df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
        for c in ("list_price", "sale_price"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["in_stock"] = df["in_stock"].astype("Int64")
    return df


def load_promos(db_path=DB_PATH) -> pd.DataFrame:
    with _conn(db_path) as con:
        df = pd.read_sql_query("SELECT * FROM promos", con)
    if not df.empty:
        df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    return df
