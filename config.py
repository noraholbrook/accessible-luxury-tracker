"""Per-brand configuration — 4 brands, full-price handbags only.

EDIT THE URLS BELOW: paste the page you land on when you click "Handbags"
on each brand's own site. Three are pre-filled with URLs that already returned
a real page in testing; Michael Kors needs the correct one.

Coach, Kate Spade, Michael Kors and Tory Burch run on Salesforce Commerce
Cloud, so they share a similar page structure.
"""
from urllib.parse import urlparse

# ---- EDIT THESE ----
CATEGORY_URLS = {
    "kate_spade":   "https://www.katespade.com/shop/handbags",
    "coach":        "https://www.coach.com/shop/women-handbags",
    "michael_kors": "https://www.michaelkors.com/women/handbags/?start=0&sz=24",
    "tory_burch":   "https://www.toryburch.com/en-us/handbags/",
}

# CSS selectors for the product grid (best-effort; the parser also falls back
# to reading dollar amounts directly, so these don't have to be perfect).
SFRA_DEFAULT = {
    "tile": "div.product-tile, li.product-tile, .product-grid .product, [data-pid]",
    "pid_attr": "data-pid",
    "title": ".pdp-link a, .product-tile-title, .link, a[href]",
    "link": ".pdp-link a, a.link, a[href]",
    "sale": ".price .sales .value, .price .sales, span.sales .value, .sales",
    "list": ".price .strike-through .value, .price del .value, .strike-through, del",
    "color": ".swatch-circle[title], .color-value",
    "new": ".product-badge, .badge-new",
}

BRANDS = {}
for _brand, _url in CATEGORY_URLS.items():
    _base = f"{urlparse(_url).scheme}://{urlparse(_url).netloc}" if _url.startswith("http") else ""
    BRANDS[_brand] = {
        "channels": {
            "full": {"method": "sfcc", "base": _base,
                     "category_url": _url, "selectors": SFRA_DEFAULT},
        },
        "promo_url": None,   # outlet/promo tracking off for now
    }

CATEGORY = "handbags"
MAX_PAGES = 1        # one page per brand while we tune; raise later
PAGE_SIZE = 48
