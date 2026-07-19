"""Upcoming Bollywood theatrical releases, from Wikipedia's
"List of Hindi films of <year>" pages.

Why Wikipedia? BookMyShow, District and Paytm all block scrapers with bot
detection, but release schedules are maintained accurately on Wikipedia.
Cards link to the film's Wikipedia page; tickets are bookable on any
platform once the film is out.

The release tables use rowspan cells: a vertical month label ("J A N"),
a day-of-month cell, then the film title in italics. We walk rows
tracking the current month/day.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from bs4 import BeautifulSoup

from .base import Event, clean, fetch

MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
)}

WINDOW_DAYS = 120  # how far ahead to show releases


def _parse_year_page(html: str, year: int) -> list[Event]:
    soup = BeautifulSoup(html, "lxml")
    events: list[Event] = []
    seen: set[str] = set()

    for table in soup.find_all("table", class_="wikitable"):
        month, day = None, None
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            for cell in cells:
                text = clean(cell.get_text())
                squashed = text.replace(" ", "").upper()
                if squashed in MONTHS:
                    month = MONTHS[squashed]
                elif re.fullmatch(r"\d{1,2}", squashed) and cell.get("rowspan"):
                    day = int(squashed)

            # Film title is the italicized cell in release tables
            i_tag = row.find("i")
            if not (i_tag and month):
                continue
            title = clean(i_tag.get_text())
            if not title or title.lower() in seen or title.upper() == "TBA":
                continue
            # A bare day cell without rowspan (single film that day)
            if not day:
                for cell in cells:
                    t = clean(cell.get_text())
                    if re.fullmatch(r"\d{1,2}", t):
                        day = int(t)
                        break

            a = i_tag.find("a", href=True)
            url = f"https://en.wikipedia.org{a['href']}" if a and a["href"].startswith("/wiki/") \
                else f"https://en.wikipedia.org/wiki/List_of_Hindi_films_of_{year}"

            try:
                release = date(year, month, day or 1)
            except ValueError:
                continue

            seen.add(title.lower())
            events.append(
                Event(
                    title=title,
                    city="All India",
                    category="Movies",
                    source="Wikipedia",
                    url=url,
                    date=release.isoformat() + "T00:00:00",
                    venue="In cinemas",
                )
            )
    return events


def scrape() -> list[Event]:
    today = date.today()
    horizon = today + timedelta(days=WINDOW_DAYS)
    events: list[Event] = []

    years = {today.year, horizon.year}
    for year in sorted(years):
        url = f"https://en.wikipedia.org/wiki/List_of_Hindi_films_of_{year}"
        print(f"  Movies: {url}")
        html = fetch(url)
        if html:
            events += _parse_year_page(html, year)

    # keep only releases from today up to the horizon
    def within(e: Event) -> bool:
        try:
            d = date.fromisoformat(e.date[:10])
            return today <= d <= horizon
        except ValueError:
            return False

    return [e for e in events if within(e)]
