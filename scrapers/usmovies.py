"""Upcoming Hollywood theatrical releases, from Wikipedia's
"List of American films of <year>" pages — the US counterpart to
scrapers/movies.py (which covers Hindi films).

The release-schedule tables here use a different layout than the Hindi
films pages: a full month name in a rowspan'd header cell (e.g.
"JANUARY"), then a rowspan'd day-of-month cell, then the film title
(italicized, linked) in its own cell. We walk rows tracking the current
month/day, same idea as movies.py but adapted to this table shape.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from bs4 import BeautifulSoup

from .base import Event, clean, fetch

MONTHS = {m: i + 1 for i, m in enumerate([
    "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
    "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
])}

WINDOW_DAYS = 120  # how far ahead to show releases
LOOKBACK_DAYS = 30  # keep recent releases visible while still likely in theaters


def _parse_year_page(html: str, year: int) -> list[Event]:
    soup = BeautifulSoup(html, "lxml")
    events: list[Event] = []
    seen: set[str] = set()

    for table in soup.find_all("table", class_="wikitable"):
        header_cells = [clean(c.get_text()) for c in table.find("tr").find_all(["td", "th"])]
        if "Opening" not in header_cells or "Title" not in header_cells:
            continue  # skip unrelated wikitables (e.g. the box-office ranking table)

        month, day = None, None
        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            idx = 0
            if cells[idx].name == "th":
                text = clean(cells[idx].get_text()).upper()
                if text in MONTHS:
                    month = MONTHS[text]
                idx += 1
            if idx < len(cells):
                text = clean(cells[idx].get_text())
                if re.fullmatch(r"\d{1,2}", text):
                    day = int(text)
                    idx += 1
            if not month or idx >= len(cells):
                continue

            title_cell = cells[idx]
            i_tag = title_cell.find("i")
            title = clean((i_tag or title_cell).get_text())
            if not title or title.lower() in seen:
                continue

            a = (i_tag or title_cell).find("a", href=True)
            url = a["href"] if a and a["href"].startswith("http") \
                else f"https://en.wikipedia.org/wiki/List_of_American_films_of_{year}"

            try:
                release = date(year, month, day or 1)
            except ValueError:
                continue

            seen.add(title.lower())
            events.append(
                Event(
                    title=title,
                    city="All USA",
                    category="Movies",
                    source="Wikipedia",
                    url=url,
                    date=release.isoformat() + "T00:00:00",
                    venue="In cinemas",
                    currency="USD",
                )
            )
    return events


def scrape() -> list[Event]:
    today = date.today()
    start = today - timedelta(days=LOOKBACK_DAYS)
    horizon = today + timedelta(days=WINDOW_DAYS)
    events: list[Event] = []

    years = {start.year, today.year, horizon.year}
    for year in sorted(years):
        url = f"https://en.wikipedia.org/wiki/List_of_American_films_of_{year}"
        print(f"  USMovies: {url}")
        html = fetch(url)
        if html:
            events += _parse_year_page(html, year)

    def within(e: Event) -> bool:
        try:
            d = date.fromisoformat(e.date[:10])
            return start <= d <= horizon
        except ValueError:
            return False

    return [e for e in events if within(e)]
