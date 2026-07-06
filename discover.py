"""Inspect a category URL and report how to scrape it.

Usage:  python discover.py https://www.katespade.com/shop/handbags

Tells you: is it Shopify? does it have JSON-LD products? a __NEXT_DATA__ blob?
how many tiles the default SFRA selector finds, and a sample of what was parsed.
Use this to finalize each brand's entry in config.py before trusting metrics.
"""
import sys, json, re
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

import fetch, parse
from config import SFRA_DEFAULT, CATEGORY


def discover(url):
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    print(f"\nInspecting {url}\n" + "-" * 60)

    # Shopify?
    sj = fetch.get(urljoin(base, "/products.json"), params={"limit": 1}, expect_json=True)
    print(f"Shopify /products.json : {'YES' if sj and 'products' in sj else 'no'}")

    html = fetch.get(url)
    if not html:
        print("Could not fetch category HTML (blocked or JS-only). "
              "Open DevTools > Network > Fetch/XHR to find the product JSON endpoint.")
        return
    soup = BeautifulSoup(html, "lxml")

    ld = soup.find_all("script", type="application/ld+json")
    ld_products = parse.parse_jsonld(html, "x", "full", CATEGORY)
    print(f"JSON-LD scripts        : {len(ld)}  (parsed products: {len(ld_products)})")
    print(f"__NEXT_DATA__ present   : {'YES' if soup.find(id='__NEXT_DATA__') else 'no'}")
    print(f"window.__INITIAL_STATE  : {'YES' if re.search(r'__INITIAL_STATE__', html) else 'no'}")

    tiles = soup.select(SFRA_DEFAULT["tile"])
    print(f"SFRA tiles (default sel): {len(tiles)}")
    grid = parse.parse_sfcc_grid(html, "x", "full", CATEGORY, SFRA_DEFAULT)
    print(f"Parsed grid records     : {len(grid)}")
    for r in (grid or ld_products)[:3]:
        print("   sample:", {k: r[k] for k in ("product_id", "title", "list_price", "sale_price", "in_stock")})

    print("\nRecommendation:")
    if sj and sj.get("products"):
        print("  -> method='shopify' (cleanest). Set shopify_collection in config.")
    elif grid:
        print("  -> method='sfcc' with default selectors (verify prices above look right).")
    elif ld_products:
        print("  -> method='sfcc'; grid selectors need tuning, but JSON-LD fallback works.")
    else:
        print("  -> JS-rendered. Find the XHR product endpoint in DevTools and add a small")
        print("     custom parser, OR use a headless browser (playwright) for this brand.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
    else:
        discover(sys.argv[1])
