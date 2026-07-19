"""Scraper for allevents.in.

AllEvents embeds schema.org JSON-LD on its listing pages, so we parse
that instead of fragile HTML selectors.
"""

from __future__ import annotations

import json

from bs4 import BeautifulSoup

from .base import Event, clean, fetch, parse_prices

# (city slug, display name, category slug, our category label)
PAGES = [
    ("bangalore", "Bangalore", "comedy", "Comedy"),
    ("bangalore", "Bangalore", "kids", "Kids"),
    ("bangalore", "Bangalore", "parties", "Nightlife"),
    ("mumbai", "Mumbai", "comedy", "Comedy"),
    ("mumbai", "Mumbai", "kids", "Kids"),
    ("new-delhi", "Delhi NCR", "comedy", "Comedy"),
    ("new-delhi", "Delhi NCR", "kids", "Kids"),
    ("hyderabad", "Hyderabad", "comedy", "Comedy"),
    ("hyderabad", "Hyderabad", "parties", "Nightlife"),
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
            if item.get("@type") == "ItemList":
                for el in item.get("itemListElement", []):
                    inner = el.get("item", el) if isinstance(el, dict) else None
                    if isinstance(inner, dict) and "Event" in str(inner.get("@type", "")):
                        yield inner
            elif "Event" in str(item.get("@type", "")):
                yield item


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

    prices = []
    offers = obj.get("offers")
    offers = offers if isinstance(offers, list) else [offers] if offers else []
    for off in offers:
        if isinstance(off, dict) and off.get("price") not in (None, ""):
            prices += parse_prices(f"₹{off['price']}") or []
            try:
                prices.append(float(off["price"]))
            except (TypeError, ValueError):
                pass

    image = obj.get("image") or ""
    if isinstance(image, list):
        image = image[0] if image else ""

    return Event(
        title=title,
        city=city,
        category=category,
        source="AllEvents",
        url=url,
        date=obj.get("startDate") or "",
        venue=venue,
        price_min=min(prices) if prices else None,
        price_max=max(prices) if prices else None,
        image=image if isinstance(image, str) else "",
    )


def fetch_price(event_url: str) -> tuple[float | None, float | None]:
    """Fetch an AllEvents detail page and pull ticket prices from its JSON-LD.

    Listing pages usually omit offers, so this is used to enrich events that
    matched a cross-source duplicate group (where price comparison matters).
    """
    html = fetch(event_url)
    if not html:
        return None, None
    prices: list[float] = []
    for obj in _iter_jsonld_events(html):
        offers = obj.get("offers")
        offers = offers if isinstance(offers, list) else [offers] if offers else []
        for off in offers:
            if isinstance(off, dict):
                for key in ("price", "lowPrice", "highPrice"):
                    try:
                        prices.append(float(off[key]))
                    except (KeyError, TypeError, ValueError):
                        pass
    if not prices:
        prices = parse_prices(html)[:5]  # fallback: first few ₹ amounts on the page
    return (min(prices), max(prices)) if prices else (None, None)


def scrape() -> list[Event]:
    events: list[Event] = []
    seen_urls: set[str] = set()
    for slug, city, cat_slug, category in PAGES:
        url = f"https://allevents.in/{slug}/{cat_slug}"
        print(f"  AllEvents: {url}")
        html = fetch(url)
        if not html:
            continue
        for obj in _iter_jsonld_events(html):
            ev = _event_from_jsonld(obj, city, category)
            if ev and ev.url not in seen_urls:
                seen_urls.add(ev.url)
                events.append(ev)
    return events
