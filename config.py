"""Per-brand configuration.

Coach, Kate Spade, Michael Kors and Tory Burch run on Salesforce Commerce
Cloud (Demandware/SFRA); Marc Jacobs is auto-detected (Shopify -> else SFCC).

IMPORTANT: the category URLs and CSS selectors below are STARTING POINTS.
Site markup changes and differs per brand theme. Run `python discover.py <url>`
on each category page to confirm the method and selectors before relying on
the numbers. Anything you haven't verified is marked TODO.

Keep the universe consistent (same category, same country site) so week-over-week
comparisons are apples-to-apples. Handbags is the cleanest universe for this pitch.
"""

# Default SFRA grid selectors — verify per brand with discover.py.
SFRA_DEFAULT = {
    "tile": "div.product-tile, .product-grid .product",
    "pid_attr": "data-pid",
    "title": ".pdp-link a, .product-tile-title, .link",
    "link": ".pdp-link a, a.link",
    "sale": ".price .sales .value, .price .sales, span.sales .value",
    "list": ".price .strike-through .value, .price del .value, .strike-through",
    "color": ".swatch-circle[title], .color-value",
    "new": ".product-badge, .badge-new",
}

BRANDS = {
    "kate_spade": {
        "channels": {
            "full":   {"method": "sfcc", "base": "https://www.katespade.com",
                       # TODO verify path + pagination param (SFRA: ?start=0&sz=48)
                       "category_url": "https://www.katespade.com/shop/handbags",
                       "selectors": SFRA_DEFAULT},
            "outlet": {"method": "sfcc", "base": "https://www.surprise.katespade.com",
                       "category_url": "https://www.surprise.katespade.com/shop/handbags",
                       "selectors": SFRA_DEFAULT},
        },
        "promo_url": "https://www.surprise.katespade.com",
    },
    "coach": {
        "channels": {
            "full":   {"method": "sfcc", "base": "https://www.coach.com",
                       "category_url": "https://www.coach.com/shop/women-handbags",
                       "selectors": SFRA_DEFAULT},
            "outlet": {"method": "sfcc", "base": "https://www.coachoutlet.com",
                       "category_url": "https://www.coachoutlet.com/shop/women-bags",
                       "selectors": SFRA_DEFAULT},
        },
        "promo_url": "https://www.coachoutlet.com",
    },
    "michael_kors": {
        "channels": {
            "full":   {"method": "sfcc", "base": "https://www.michaelkors.com",
                       "category_url": "https://www.michaelkors.com/women/handbags/_/N-28ei",
                       "selectors": SFRA_DEFAULT},
            # MK online outlet lives under a /outlet path; verify.
            "outlet": {"method": "sfcc", "base": "https://www.michaelkors.com",
                       "category_url": "https://www.michaelkors.com/outlet/handbags/_/N-...",
                       "selectors": SFRA_DEFAULT},
        },
        "promo_url": "https://www.michaelkors.com/outlet",
    },
    "tory_burch": {
        "channels": {
            "full":   {"method": "sfcc", "base": "https://www.toryburch.com",
                       "category_url": "https://www.toryburch.com/en-us/handbags/",
                       "selectors": SFRA_DEFAULT},
            # TB's online outlet is limited; sale section is the practical proxy.
            "outlet": {"method": "sfcc", "base": "https://www.toryburch.com",
                       "category_url": "https://www.toryburch.com/en-us/sale/handbags/",
                       "selectors": SFRA_DEFAULT},
        },
        "promo_url": "https://www.toryburch.com/en-us/sale/",
    },
    "marc_jacobs": {
        "channels": {
            # auto: tries Shopify /products.json, else SFCC/JSON-LD
            "full":   {"method": "auto", "base": "https://www.marcjacobs.com",
                       "category_url": "https://www.marcjacobs.com/handbags",
                       "shopify_collection": "handbags",
                       "selectors": SFRA_DEFAULT},
        },
        "promo_url": "https://www.marcjacobs.com/sale",
    },
}

CATEGORY = "handbags"      # the tracked universe
MAX_PAGES = 1              # pagination safety cap per category
PAGE_SIZE = 48            # SFRA sz param
