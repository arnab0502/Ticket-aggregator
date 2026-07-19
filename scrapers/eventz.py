"""Scraper for eventz.co.in.

The site is built on Wix, so instead of relying on CSS classes (which are
auto-generated and change), we walk the page's visible text in order.
Each event card renders as a run of strings:

    ₹399 / Corporate Majdoor by Anmol Garg / The Art Gully Studio,
    Bengaluru / Saturday, 13 June 2026 / Comedy Shows

So: a price marker starts a card; the next strings are title, venue,
date, category — with the date recognizable by its fixed format.
"""

from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from .base import Event, clean, fetch, parse_prices

PAGES = [
    ("https://www.eventz.co.in/comedy-shows-in-bangalore", "Bangalore", "Comedy"),
    ("https://www.eventz.co.in/comedy-shows-in-mumbai", "Mumbai", "Comedy"),
    ("https://www.eventz.co.in/comedy-shows-in-delhi", "Delhi NCR", "Comedy"),
    ("https://www.eventz.co.in/comedy-shows-in-hyderabad", "Hyderabad", "Comedy"),
    ("https://www.eventz.co.in/kids-events-in-bengaluru", "Bangalore", "Kids"),
]

PRICE_ONLY_RE = re.compile(r"^₹\s*[\d,]+$")
DATE_RE = re.compile(r"^[A-Z][a-z]+day,\s+\d{1,2}\s+[A-Z][a-z]+\s+\d{4}$")
SKIP_TITLES = {"venues", "services", "contact", "categories", "list your event"}


def _parse_date(text: str) -> str:
    try:
        return datetime.strptime(text, "%A, %d %B %Y").strftime("%Y-%m-%dT00:00:00")
    except ValueError:
        return text


def _parse_listing(html: str, page_url: str, city: str, category: str) -> list[Event]:
    soup = BeautifulSoup(html, "lxml")
    strings = [clean(s) for s in soup.stripped_strings if clean(s)]

    events: list[Event] = []
    i = 0
    while i < len(strings):
        if not PRICE_ONLY_RE.match(strings[i]):
            i += 1
            continue

        prices = parse_prices(strings[i])
        # Collect the next few strings until the date marker
        title, venue, date = "", "", ""
        j = i + 1
        chunk: list[str] = []
        while j < len(strings) and j < i + 8:
            if DATE_RE.match(strings[j]):
                date = _parse_date(strings[j])
                break
            if not PRICE_ONLY_RE.match(strings[j]):
                chunk.append(strings[j])
            j += 1

        if chunk:
            title = chunk[0]
            venue = chunk[1] if len(chunk) > 1 else ""

        if (
            title
            and title.lower() not in SKIP_TITLES
            and not title.lower().startswith("image by")
            and len(title) > 3
        ):
            events.append(
                Event(
                    title=title,
                    city=city,
                    category=category,
                    source="Eventz",
                    url=page_url,
                    date=date,
                    venue=venue,
                    price_min=min(prices) if prices else None,
                    price_max=max(prices) if prices else None,
                )
            )
        i = j + 1
    return events


def scrape() -> list[Event]:
    events: list[Event] = []
    for url, city, category in PAGES:
        print(f"  Eventz: {url}")
        html = fetch(url)
        if html:
            found = _parse_listing(html, url, city, category)
            events += found
    return events
