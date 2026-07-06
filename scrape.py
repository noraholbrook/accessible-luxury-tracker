"""Turns config -> normalized observation rows for a brand/channel."""
from urllib.parse import urljoin
import json

import config
import fetch
import parse


def _abs(base, records):
    for r in records:
        if r.get("url") and r["url"].startswith("/"):
            r["url"] = urljoin(base, r["url"])
    return records


def scrape_channel(brand, channel, cfg):
    method, base = cfg["method"], cfg["base"]
    cat_url = cfg["category_url"]
    records = []

    if method in ("shopify", "auto"):
        coll = cfg.get("shopify_collection")
        url = urljoin(base, f"/collections/{coll}/products.json" if coll else "/products.json")
        for page in range(1, config.MAX_PAGES + 1):
            data = fetch.get(url, params={"limit": 250, "page": page}, expect_json=True)
            if not data or not data.get("products"):
                break
            records += parse.parse_shopify(data, brand, channel, config.CATEGORY)
        if records:
            return _abs(base, records)
        if method == "shopify":
            return records
        # auto -> fall through to sfcc/jsonld

    # SFRA/SFCC grid, paginated with ?start=&sz=
    for page in range(config.MAX_PAGES):
        params = {"start": page * config.PAGE_SIZE, "sz": config.PAGE_SIZE}
        html = fetch.get(cat_url, params=params)
        if not html:
            break
        page_rows = parse.parse_sfcc_grid(html, brand, channel, config.CATEGORY, cfg["selectors"])
        if not page_rows:
            # fallback: JSON-LD embedded in the grid/PDP
            page_rows = parse.parse_jsonld(html, brand, channel, config.CATEGORY)
        if not page_rows:
            break
        records += page_rows
        if len(page_rows) < config.PAGE_SIZE:
            break
    # de-dupe on (product_id, variant_id)
    seen, uniq = set(), []
    for r in records:
        k = (r["product_id"], r["variant_id"])
        if k not in seen:
            seen.add(k); uniq.append(r)
    return _abs(base, uniq)


def scrape_promo(brand, cfg_brand):
    url = cfg_brand.get("promo_url")
    if not url:
        return None
    html = fetch.get(url)
    if not html:
        return None
    p = parse.detect_promo(html)
    p.update(brand=brand, channel="outlet")
    return p
