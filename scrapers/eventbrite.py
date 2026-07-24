"""Scraper for eventbrite.com — the US equivalent of allevents.in.

Eventbrite's city/category browse pages embed the same kind of schema.org
JSON-LD ItemList that allevents.in does, so this mirrors the parsing
approach in scrapers/allevents.py. Unlike AllEvents, Eventbrite's listing
pages never include an `offers`/price field, so every event here starts
priced "See listing" (no per-event detail-page enrichment is done).
"""

from __future__ import annotations

import json

from bs4 import BeautifulSoup

from .base import Event, clean, fetch

# (geo slug, display city, category slug, our category label)
PAGES = [
    ("ca--sacramento", "Sacramento", "comedy--events", "Comedy"),
    ("ca--sacramento", "Sacramento", "family--events", "Kids"),
    ("ca--sacramento", "Sacramento", "nightlife--events", "Nightlife"),
    ("ca--sacramento", "Sacramento", "market--events", "Markets"),
    ("ca--san-francisco", "San Francisco", "comedy--events", "Comedy"),
    ("ca--san-francisco", "San Francisco", "family--events", "Kids"),
    ("ca--san-francisco", "San Francisco", "nightlife--events", "Nightlife"),
    ("ca--san-francisco", "San Francisco", "market--events", "Markets"),
    ("ny--new-york", "New York City", "comedy--events", "Comedy"),
    ("ny--new-york", "New York City", "family--events", "Kids"),
    ("ny--new-york", "New York City", "nightlife--events", "Nightlife"),
    ("ny--new-york", "New York City", "market--events", "Markets"),
    ("il--chicago", "Chicago", "comedy--events", "Comedy"),
    ("il--chicago", "Chicago", "family--events", "Kids"),
    ("il--chicago", "Chicago", "nightlife--events", "Nightlife"),
    ("il--chicago", "Chicago", "market--events", "Markets"),
]


def _iter_jsonld_events(html: str):
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            for el in item.get("itemListElement", []):
                inner = el.get("item", el) if isinstance(el, dict) else None
                if isinstance(inner, dict) and "Event" in str(inner.get("@type", "")):
                    yield inner


def _event_from_jsonld(obj: dict, city: str, category: str) -> Event | None:
    title = clean(obj.get("name") or "")
    url = obj.get("url") or ""
    if not title or not url:
        return None

    venue = ""
    loc = obj.get("location")
    if isinstance(loc, dict):
        venue = loc.get("name") or ""
    elif isinstance(loc, list) and loc and isinstance(loc[0], dict):
        venue = loc[0].get("name") or ""

    image = obj.get("image") or ""
    if isinstance(image, list):
        image = image[0] if image else ""

    return Event(
        title=title,
        city=city,
        category=category,
        source="Eventbrite",
        url=url,
        date=obj.get("startDate") or "",
        venue=venue,
        currency="USD",
        image=image if isinstance(image, str) else "",
    )


def scrape() -> list[Event]:
    events: list[Event] = []
    seen_urls: set[str] = set()
    for slug, city, cat_slug, category in PAGES:
        url = f"https://www.eventbrite.com/d/{slug}/{cat_slug}/"
        print(f"  Eventbrite: {url}")
        html = fetch(url)
        if not html:
            continue
        for obj in _iter_jsonld_events(html):
            ev = _event_from_jsonld(obj, city, category)
            if ev and ev.url not in seen_urls:
                seen_urls.add(ev.url)
                events.append(ev)
    return events
