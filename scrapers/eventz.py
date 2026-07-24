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
    """Each card's title/venue/date/price render as plain text (see module
    docstring), but the card also wraps an <a href="…/events-list/<slug>">
    around its thumbnail image — that's the event's real detail page. So
    for each such link we walk up to the smallest ancestor whose text
    contains both a price marker and a date (i.e. the card container),
    then parse that container's text exactly as before.
    """
    soup = BeautifulSoup(html, "lxml")
    events: list[Event] = []
    seen_urls: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/events-list/" not in href or href in seen_urls:
            continue

        container, strings = a, []
        for _ in range(6):
            container = container.parent
            if container is None:
                break
            strings = [clean(s) for s in container.stripped_strings if clean(s)]
            if any(PRICE_ONLY_RE.match(s) for s in strings) and any(DATE_RE.match(s) for s in strings):
                break
        else:
            continue
        if not strings:
            continue

        price_idx = next((i for i, s in enumerate(strings) if PRICE_ONLY_RE.match(s)), None)
        if price_idx is None:
            continue
        prices = parse_prices(strings[price_idx])

        title, venue, date = "", "", ""
        chunk: list[str] = []
        j = price_idx + 1
        while j < len(strings) and j < price_idx + 8:
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
            seen_urls.add(href)
            events.append(
                Event(
                    title=title,
                    city=city,
                    category=category,
                    source="Eventz",
                    url=href,
                    date=date,
                    venue=venue,
                    price_min=min(prices) if prices else None,
                    price_max=max(prices) if prices else None,
                )
            )
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
