"""HTTP layer. Routes through ScraperAPI when SCRAPERAPI_KEY is set.

ScraperAPI fetches the target on its own infrastructure (proxies + a real
browser via render=true), which is what gets past JS/bot challenges. We never
hardcode the key — it's read from the environment (a GitHub Actions secret).

If no key is set, it falls back to a direct, robots-respecting fetch.
"""
import os
import time
import urllib.robotparser as robotparser
from urllib.parse import urlparse, urlencode

import requests

API_KEY = os.getenv("SCRAPERAPI_KEY", "").strip()
API_ENDPOINT = "https://api.scraperapi.com/"
RENDER = os.getenv("SCRAPERAPI_RENDER", "true")   # "true" costs more credits but beats JS challenges
COUNTRY = os.getenv("SCRAPERAPI_COUNTRY", "us")

USER_AGENT = "BrandTracker/1.0 (research)"
MIN_DELAY_SEC = 1.0
TIMEOUT = 70
RESPECT_ROBOTS = True   # only applies to direct (no-key) mode

_last = {}
_robots = {}
_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})


def using_api() -> bool:
    return bool(API_KEY)


def _robots_ok(url):
    if not RESPECT_ROBOTS:
        return True
    host = urlparse(url).netloc
    if host not in _robots:
        rp = robotparser.RobotFileParser()
        rp.set_url(f"{urlparse(url).scheme}://{host}/robots.txt")
        try:
            rp.read()
        except Exception:
            rp = None
        _robots[host] = rp
    rp = _robots[host]
    return True if rp is None else rp.can_fetch(USER_AGENT, url)


def _throttle(host):
    wait = MIN_DELAY_SEC - (time.time() - _last.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    _last[host] = time.time()


def _wrap(target):
    """Build the ScraperAPI request URL around a target URL."""
    payload = {"api_key": API_KEY, "url": target, "render": RENDER}
    if COUNTRY:
        payload["country_code"] = COUNTRY
    return API_ENDPOINT + "?" + urlencode(payload)


def get(url, params=None, tries=3, expect_json=False):
    # fold any query params into the target URL first
    if params:
        url = url + ("&" if "?" in url else "?") + urlencode(params)

    if using_api():
        request_url = _wrap(url)          # ScraperAPI handles proxies/rendering/challenges
    else:
        if not _robots_ok(url):
            print(f"  [robots] disallowed, skipping: {url}")
            return None
        request_url = url

    host = urlparse(url).netloc
    for attempt in range(1, tries + 1):
        _throttle("scraperapi" if using_api() else host)
        try:
            r = _session.get(request_url, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.json() if expect_json else r.text
            if r.status_code in (403, 429, 500):
                print(f"  [{r.status_code}] {url} (attempt {attempt})")
                time.sleep(4 * attempt)
                continue
            print(f"  [{r.status_code}] {url}")
            return None
        except requests.RequestException as e:
            print(f"  [error] {e} (attempt {attempt})")
            time.sleep(3 * attempt)
    return None
