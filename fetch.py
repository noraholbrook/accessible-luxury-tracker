"""Polite HTTP layer: robots.txt respect, rate limiting, retries.

Scraping public pricing pages is common in equity research, but it can run
against a site's Terms of Service. This module defaults to conservative,
respectful behaviour. See README for the legal/ToS notes.
"""
import time
import random
import urllib.robotparser as robotparser
from urllib.parse import urlparse

import requests

USER_AGENT = (
    "TapestryResearchTracker/1.0 (equity research; contact: you@example.com)"
)
MIN_DELAY_SEC = 3.0        # be gentle: >=1 request / 3s per host
TIMEOUT = 30
RESPECT_ROBOTS = True

_last_hit = {}
_robots_cache = {}
_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})


def _robots_ok(url: str) -> bool:
    if not RESPECT_ROBOTS:
        return True
    host = urlparse(url).netloc
    if host not in _robots_cache:
        rp = robotparser.RobotFileParser()
        rp.set_url(f"{urlparse(url).scheme}://{host}/robots.txt")
        try:
            rp.read()
        except Exception:
            rp = None
        _robots_cache[host] = rp
    rp = _robots_cache[host]
    return True if rp is None else rp.can_fetch(USER_AGENT, url)


def _throttle(url: str):
    host = urlparse(url).netloc
    wait = MIN_DELAY_SEC - (time.time() - _last_hit.get(host, 0))
    if wait > 0:
        time.sleep(wait + random.uniform(0, 0.7))
    _last_hit[host] = time.time()


def get(url: str, params=None, tries=3, expect_json=False):
    """GET with robots check, throttle, and simple backoff. Returns text/json or None."""
    if not _robots_ok(url):
        print(f"  [robots] disallowed, skipping: {url}")
        return None
    for attempt in range(1, tries + 1):
        _throttle(url)
        try:
            r = _session.get(url, params=params, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.json() if expect_json else r.text
            if r.status_code in (403, 429):
                print(f"  [{r.status_code}] blocked/rate-limited on {url} (attempt {attempt})")
                time.sleep(5 * attempt)
                continue
            print(f"  [{r.status_code}] {url}")
            return None
        except requests.RequestException as e:
            print(f"  [error] {e} (attempt {attempt})")
            time.sleep(3 * attempt)
    return None
