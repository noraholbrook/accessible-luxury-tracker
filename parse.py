"""Extractors that turn a page into normalized variant records.

Three strategies, in order of reliability:
  1. Shopify  -> /products.json (clean, structured)            [Marc Jacobs may be here]
  2. JSON-LD  -> <script type="application/ld+json"> Product   [works on many PDPs]
  3. SFCC/SFRA grid tiles -> configurable CSS selectors        [Coach/KS/MK/TB]

Each returns a list of dicts with the observation fields (minus snapshot_date,
which run_weekly stamps on). Availability is often absent on grid pages; see the
README for how to get reliable in_stock (PDP JSON-LD offers.availability).
"""
import json
import re
from bs4 import BeautifulSoup

_PCT = re.compile(r"(\d{1,2})\s*%\s*off", re.I)
_PROMO_HINTS = re.compile(
    r"(extra|take|up to|save)\s+\d+%|(\d+%\s*off)|sitewide|clearance|"
    r"friends?\s*&?\s*family|flash sale|code\s+[A-Z0-9]{3,}", re.I)


# ---------- 1. Shopify ----------
def parse_shopify(products_json, brand, channel, category):
    out = []
    for p in products_json.get("products", []):
        pid = str(p.get("id"))
        title = p.get("title")
        tags = " ".join(p.get("tags", [])) if isinstance(p.get("tags"), list) else str(p.get("tags", ""))
        is_new = 1 if re.search(r"\bnew\b", tags, re.I) else 0
        handle = p.get("handle", "")
        for v in p.get("variants", []):
            price = _f(v.get("price"))
            compare = _f(v.get("compare_at_price")) or price
            out.append(dict(
                brand=brand, channel=channel, category=category,
                product_id=pid, variant_id=str(v.get("id")),
                title=title, color=v.get("option1"),
                url=f"/products/{handle}",
                list_price=compare, sale_price=price,
                in_stock=1 if v.get("available") else 0,
                is_new_flag=is_new))
    return out


# ---------- 2. JSON-LD ----------
def parse_jsonld(html, brand, channel, category):
    soup = BeautifulSoup(html, "lxml")
    out = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "{}")
        except Exception:
            continue
        for node in _iter_products(data):
            offers = node.get("offers") or {}
            offers = offers[0] if isinstance(offers, list) and offers else offers
            price = _f(offers.get("price"))
            list_price = _f(offers.get("highPrice")) or price
            avail = str(offers.get("availability", "")).lower()
            out.append(dict(
                brand=brand, channel=channel, category=category,
                product_id=str(node.get("productID") or node.get("sku") or node.get("name")),
                variant_id=str(node.get("sku") or node.get("color") or "default"),
                title=node.get("name"), color=node.get("color"),
                url=node.get("url"),
                list_price=list_price, sale_price=price,
                in_stock=0 if "outofstock" in avail else (1 if "instock" in avail else None),
                is_new_flag=None))
    return out


def _iter_products(data):
    if isinstance(data, dict):
        if data.get("@type") in ("Product", "ProductGroup"):
            yield data
        for v in data.values():
            yield from _iter_products(v)
    elif isinstance(data, list):
        for v in data:
            yield from _iter_products(v)


# ---------- 3. SFCC / SFRA grid tiles ----------
def parse_sfcc_grid(html, brand, channel, category, sel):
    """sel: dict of CSS selectors for this brand's theme (see config.SELECTORS).
    Verify with discover.py before trusting output."""
    soup = BeautifulSoup(html, "lxml")
    out = []
    for tile in soup.select(sel["tile"]):
        pid = tile.get(sel.get("pid_attr", "data-pid")) or _txt(tile, sel.get("pid"))
        if not pid:
            continue
        sale = _price(tile, sel.get("sale"))
        lst = _price(tile, sel.get("list")) or sale
        out.append(dict(
            brand=brand, channel=channel, category=category,
            product_id=str(pid),
            variant_id=_txt(tile, sel.get("color")) or "default",
            title=_txt(tile, sel.get("title")),
            color=_txt(tile, sel.get("color")),
            url=_attr(tile, sel.get("link"), "href"),
            list_price=lst, sale_price=sale,
            in_stock=None,  # grids rarely expose stock; enrich via PDP if needed
            is_new_flag=1 if sel.get("new") and tile.select_one(sel["new"]) else 0))
    return out


# ---------- promo detector ----------
def detect_promo(html):
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)[:6000]
    hits = _PROMO_HINTS.findall(text)
    pcts = [int(x) for x in _PCT.findall(text)]
    active = bool(hits) or bool(pcts)
    snippet = ""
    m = _PROMO_HINTS.search(text)
    if m:
        i = m.start()
        snippet = text[max(0, i - 30): i + 70].strip()
    return dict(promo_active=1 if active else 0,
                promo_text=snippet[:200],
                promo_max_pct=float(max(pcts)) if pcts else None)


# ---------- helpers ----------
def _f(x):
    try:
        return float(str(x).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None

def _txt(node, sel):
    if not sel: return None
    el = node.select_one(sel)
    return el.get_text(strip=True) if el else None

def _attr(node, sel, attr):
    if not sel: return None
    el = node.select_one(sel)
    return el.get(attr) if el else None

def _price(node, sel):
    if not sel: return None
    el = node.select_one(sel)
    if not el: return None
    # prefer a content= attribute (SFRA puts machine price there), else text
    return _f(el.get("content")) or _f(el.get_text())
