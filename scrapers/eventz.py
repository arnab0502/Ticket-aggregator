"""Scraper for eventz.co.in.

Their markup changes now and then, so this parser is deliberately
defensive: it looks for event links plus nearby text and prices, and
returns nothing (rather than crashing) if the page shape changes.
"""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import Event, fetch, parse_prices

PAGES = [
    ("https://www.eventz.co.in/comedy-shows-in-bangalore", "Bangalore", "Comedy"),
    ("https://www.eventz.co.in/comedy-shows-in-mumbai", "Mumbai", "Comedy"),
    ("https://www.eventz.co.in/comedy-shows-in-delhi", "Delhi NCR", "Comedy"),
    ("https://www.eventz.co.in/comedy-shows-in-hyderabad", "Hyderabad", "Comedy"),
]


def _parse_listing(html: str, base_url: str, city: str, category: str) -> list[Event]:
    soup = BeautifulSoup(html, "lxml")
    events: list[Event] = []
    seen: set[str] = set()

    # Event detail links generally contain "/event" or end with "-tickets"
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not ("/event" in href or href.rstrip("/").endswith("-tickets")):
            continue
        url = urljoin(base_url, href)
        if url in seen:
            continue

        # The card is usually the nearest ancestor with a decent chunk of text
        card = a
        for _ in range(3):
            if card.parent and len(card.parent.get_text(strip=True)) < 400:
                card = card.parent
        text = card.get_text(" ", strip=True)

        title = a.get_text(strip=True) or (a.img.get("alt", "") if a.img else "")
        if not title or len(title) < 4:
            continue

        prices = parse_prices(text)
        img = card.find("img")
        events.append(
            Event(
                title=title,
                city=city,
                category=category,
                source="Eventz",
                url=url,
                venue="",
                price_min=min(prices) if prices else None,
                price_max=max(prices) if prices else None,
                image=img.get("src", "") if img else "",
            )
        )
        seen.add(url)
    return events


def scrape() -> list[Event]:
    events: list[Event] = []
    for url, city, category in PAGES:
        print(f"  Eventz: {url}")
        html = fetch(url)
        if html:
            events += _parse_listing(html, url, city, category)
    return events
