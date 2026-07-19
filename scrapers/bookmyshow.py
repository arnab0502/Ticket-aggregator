"""Scraper for BookMyShow (best-effort).

BookMyShow sits behind Akamai bot protection and blocks nearly all
automated requests, so expect this to return nothing most runs — it
tries the public pages and parses schema.org JSON-LD if a response gets
through, and fails quietly otherwise.

BookMyShow still appears on the dashboard regardless: movie cards get a
BookMyShow booking chip (see aggregator/dashboard.py), because that's
where users actually buy tickets.

If you need reliable BMS data, the honest options are their partner
API (https://in.bookmyshow.com — business tie-ups) or a headless
browser like Playwright with manual captcha solving. PRs welcome.
"""

from __future__ import annotations

import json

from bs4 import BeautifulSoup

from .base import Event, clean, fetch

PAGES = [
    ("https://in.bookmyshow.com/explore/events-bengaluru", "Bangalore"),
    ("https://in.bookmyshow.com/explore/events-mumbai", "Mumbai"),
    ("https://in.bookmyshow.com/explore/events-national-capital-region-ncr", "Delhi NCR"),
    ("https://in.bookmyshow.com/explore/events-hyderabad", "Hyderabad"),
]


def _parse_jsonld(html: str, city: str) -> list[Event]:
    events: list[Event] = []
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not (isinstance(item, dict) and "Event" in str(item.get("@type", ""))):
                continue
            title = clean(item.get("name") or "")
            url = item.get("url") or ""
            if not title or not url:
                continue
            offers = item.get("offers") or {}
            price = None
            if isinstance(offers, dict):
                try:
                    price = float(offers.get("price") or offers.get("lowPrice"))
                except (TypeError, ValueError):
                    pass
            loc = item.get("location") or {}
            events.append(
                Event(
                    title=title,
                    city=city,
                    category="Comedy" if "comedy" in title.lower() else "Other",
                    source="BookMyShow",
                    url=url,
                    date=item.get("startDate") or "",
                    venue=loc.get("name", "") if isinstance(loc, dict) else "",
                    price_min=price,
                    price_max=price,
                )
            )
    return events


def scrape() -> list[Event]:
    events: list[Event] = []
    for url, city in PAGES:
        print(f"  BookMyShow: {url} (usually blocked — best-effort)")
        html = fetch(url)
        if html:
            events += _parse_jsonld(html, city)
    if not events:
        print("  BookMyShow blocked automated access (expected). "
              "Movie cards still link to BMS for booking.")
    return events
