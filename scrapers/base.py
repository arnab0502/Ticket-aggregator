"""Shared helpers and the Event model used by every scraper."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, asdict, field

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

REQUEST_DELAY_SECONDS = 1.5  # be polite to the sites we scrape


@dataclass
class Event:
    title: str
    city: str
    category: str
    source: str
    url: str
    date: str = ""          # ISO 8601 if known, else free text
    venue: str = ""
    price_min: float | None = None
    price_max: float | None = None
    currency: str = "INR"
    image: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


_last_request_at = 0.0


def fetch(url: str, timeout: int = 20) -> str | None:
    """GET a page politely (rate-limited). Returns HTML or None on failure."""
    global _last_request_at
    wait = REQUEST_DELAY_SECONDS - (time.time() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        _last_request_at = time.time()
        if resp.status_code == 200:
            return resp.text
        print(f"  ! {url} -> HTTP {resp.status_code}")
    except requests.RequestException as exc:
        print(f"  ! {url} -> {exc}")
    return None


PRICE_RE = re.compile(r"(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)


def parse_prices(text: str) -> list[float]:
    """Extract all rupee amounts from a blob of text."""
    out = []
    for m in PRICE_RE.finditer(text or ""):
        try:
            out.append(float(m.group(1).replace(",", "")))
        except ValueError:
            pass
    return out
