"""Extractors that turn a page into normalized variant records.

Price handling is deliberately forgiving: for each product tile we read every
dollar amount present. Two distinct amounts => on sale (higher = original,
lower = current); one amount => full price. This avoids brittle per-site price
selectors. A one-time diagnostic prints the first tile's HTML so selectors can
be confirmed against the real markup.
"""
import json
import re
from bs4 import BeautifulSoup

PRICE_RE = re.compile(r"\$\s?([0-9][0-9,]*(?:\.[0-9]{2})?)")
TILE_SEL = "div.product-tile, li.product-tile, .product-grid .product, [data-pid], article.product, .product-tile-wrapper"
_diag_done = False


def _prices_in(text):
    out = []
    for m in PRICE_RE.findall(text or ""):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def parse_sfcc_grid(html, brand, channel, category, sel):
    global _diag_done
    soup = BeautifulSoup(html, "lxml")
    tiles = soup.select(TILE_SEL)

    if not _diag_done:
        _diag_done = True
        n_ld = len(soup.find_all("script", type="application/ld+json"))
        print(f"    [diag] {brand}: {len(tiles)} tiles found; {n_ld} JSON-LD blocks", flush=True)
        if tiles:
            snippet = " ".join(str(tiles[0]).split())[:800]
            print(f"    [diag] first tile HTML: {snippet}", flush=True)

    out, seen = [], set()
    for tile in tiles:
        pid = tile.get(sel.get("pid_attr", "data-pid"))
        link = tile.select_one(sel.get("link", "a[href]"))
        href = link.get("href") if link else None
        if not pid:
            pid = (href or "").rstrip("/").split("/")[-1].split("?")[0] or None
        if not pid:
            continue
        if pid in seen:
            continue
        seen.add(pid)

        # price: try selectors, then fall back to any $ amounts in the tile
        sale = _price(tile, sel.get("sale"))
        lst = _price(tile, sel.get("list"))
        if sale is None or lst is None:
            ps = sorted(set(_prices_in(tile.get_text(" ", strip=True))))
            if ps:
                sale = sale if sale is not None else ps[0]
                lst = lst if lst is not None else ps[-1]
        title = _txt(tile, sel.get("title"))
        out.append(dict(
            brand=brand, channel=channel, category=category,
            product_id=str(pid), variant_id="std",
            title=title, color=None, url=href,
            list_price=lst, sale_price=sale,
            in_stock=1,  # grids rarely mark OOS; assume in stock
            is_new_flag=1 if sel.get("new") and tile.select_one(sel["new"]) else 0))
    return out


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
            if price is None:
                continue
            out.append(dict(
                brand=brand, channel=channel, category=category,
                product_id=str(node.get("productID") or node.get("sku") or node.get("name")),
                variant_id=str(node.get("sku") or "std"),
                title=node.get("name"), color=node.get("color"), url=node.get("url"),
                list_price=list_price, sale_price=price,
                in_stock=0 if "outofstock" in avail else 1, is_new_flag=0))
    return out


def parse_shopify(products_json, brand, channel, category):
    out = []
    for p in products_json.get("products", []):
        for v in p.get("variants", []):
            price = _f(v.get("price"))
            out.append(dict(
                brand=brand, channel=channel, category=category,
                product_id=str(p.get("id")), variant_id=str(v.get("id")),
                title=p.get("title"), color=v.get("option1"),
                url=f"/products/{p.get('handle','')}",
                list_price=_f(v.get("compare_at_price")) or price, sale_price=price,
                in_stock=1 if v.get("available") else 0, is_new_flag=0))
    return out


def detect_promo(html):
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)[:6000]
    pcts = [int(x) for x in re.findall(r"(\d{1,2})\s*%\s*off", text, re.I)]
    return dict(promo_active=1 if pcts else 0,
                promo_text=(f"up to {max(pcts)}% off" if pcts else ""),
                promo_max_pct=float(max(pcts)) if pcts else None)


def _iter_products(data):
    if isinstance(data, dict):
        if data.get("@type") in ("Product", "ProductGroup"):
            yield data
        for v in data.values():
            yield from _iter_products(v)
    elif isinstance(data, list):
        for v in data:
            yield from _iter_products(v)


def _f(x):
    try:
        return float(str(x).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None

def _txt(node, css):
    if not css:
        return None
    el = node.select_one(css)
    return el.get_text(strip=True) if el else None

def _price(node, css):
    if not css:
        return None
    el = node.select_one(css)
    if not el:
        return None
    return _f(el.get("content")) or (_prices_in(el.get_text(" ", strip=True)) or [None])[0]
