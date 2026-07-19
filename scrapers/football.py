"""Football fixtures for EPL, Bundesliga, La Liga, Ligue 1 and ISL,
with ticketing links per match.

Fixtures come from ESPN's public scoreboard API (free, no key needed):
    https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard

Ticket marketplaces (StubHub, Ticketmaster, viagogo, SeatGeek) all block
automated scraping, so instead of scraped prices each match card links
to a pre-built search on every marketplace, plus the home club's
official ticket office where known — official sale is always the
cheapest and safest starting point.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from urllib.parse import quote

from .base import Event, clean, fetch

WINDOW_DAYS = 60

LEAGUES = [
    ("eng.1", "EPL"),
    ("ger.1", "Bundesliga"),
    ("esp.1", "La Liga"),
    ("fra.1", "Ligue 1"),
    ("ind.1", "ISL"),
]

# Official ticket offices for popular clubs (home team → URL).
# Buying from the club is always the safest and usually cheapest option.
OFFICIAL_TICKETS = {
    # EPL
    "Arsenal": "https://www.arsenal.com/tickets",
    "Chelsea": "https://www.chelseafc.com/en/tickets",
    "Liverpool": "https://www.liverpoolfc.com/tickets",
    "Manchester United": "https://www.manutd.com/en/tickets-and-hospitality",
    "Manchester City": "https://www.mancity.com/tickets",
    "Tottenham Hotspur": "https://www.tottenhamhotspur.com/tickets/",
    "Newcastle United": "https://www.newcastleunited.com/en/tickets",
    "Aston Villa": "https://www.avfc.co.uk/tickets/",
    "West Ham United": "https://www.whufc.com/tickets",
    "Everton": "https://www.evertonfc.com/tickets",
    # Bundesliga
    "Bayern Munich": "https://fcbayern.com/en/tickets",
    "Borussia Dortmund": "https://www.bvb.de/eng/Tickets",
    "RB Leipzig": "https://www.rbleipzig.com/en/tickets",
    "Bayer Leverkusen": "https://www.bayer04.de/en-us/page/tickets",
    "Eintracht Frankfurt": "https://tickets.eintracht.de",
    # La Liga
    "Real Madrid": "https://www.realmadrid.com/en/tickets",
    "Barcelona": "https://www.fcbarcelona.com/en/tickets",
    "Atlético Madrid": "https://www.atleticodemadrid.com/en/tickets",
    "Atletico Madrid": "https://www.atleticodemadrid.com/en/tickets",
    "Sevilla": "https://www.sevillafc.es/en/tickets",
    "Athletic Club": "https://www.athletic-club.eus/en/tickets",
    # Ligue 1
    "PSG": "https://tickets.psg.fr",
    "Paris Saint-Germain": "https://tickets.psg.fr",
    "Marseille": "https://billetterie.om.fr",
    "Lyon": "https://billetterie.ol.fr",
    "Monaco": "https://tickets.asmonaco.com",
    "Lille": "https://billetterie.losc.fr",
}


def _parse_scoreboard(payload: dict, league_label: str) -> list[Event]:
    events: list[Event] = []
    for ev in payload.get("events", []):
        name = clean(ev.get("name") or "")
        when = ev.get("date") or ""
        comp = (ev.get("competitions") or [{}])[0]

        venue = ""
        v = comp.get("venue") or {}
        if v.get("fullName"):
            venue = v["fullName"]
            city = (v.get("address") or {}).get("city")
            if city:
                venue += f", {city}"

        home = away = ""
        for c in comp.get("competitors", []):
            team = clean((c.get("team") or {}).get("displayName") or "")
            if c.get("homeAway") == "home":
                home = team
            elif c.get("homeAway") == "away":
                away = team
        title = f"{home} vs {away}" if home and away else name
        if not title:
            continue

        extra = {"league": league_label, "home": home, "away": away}
        if home in OFFICIAL_TICKETS:
            extra["official_url"] = OFFICIAL_TICKETS[home]

        events.append(
            Event(
                title=title,
                city=league_label,          # league doubles as the filter pill
                category="Football",
                source="ESPN",
                url=ev.get("links", [{}])[0].get("href", "https://www.espn.in/football/"),
                date=when.replace("Z", "+00:00"),
                venue=venue,
                extra=extra,
            )
        )
    return events


PRICE_ENRICH_CAP = 40  # max matches to look up per marketplace API


def _enrich_seatgeek(events: list[Event]) -> None:
    """Live resale prices from SeatGeek's official free API.

    Get a client id at https://seatgeek.com/account/develop then:
        export SEATGEEK_CLIENT_ID=your_id
    Prices are in USD.
    """
    key = os.environ.get("SEATGEEK_CLIENT_ID")
    if not key:
        print("  (set SEATGEEK_CLIENT_ID for live resale prices — free key at seatgeek.com/account/develop)")
        return
    for ev in events[:PRICE_ENRICH_CAP]:
        url = f"https://api.seatgeek.com/2/events?client_id={key}&q={quote(ev.title)}&per_page=1"
        raw = fetch(url)
        if not raw:
            continue
        try:
            hits = json.loads(raw).get("events") or []
            stats = hits[0].get("stats") or {}
            lo, hi = stats.get("lowest_price"), stats.get("highest_price")
            if lo:
                ev.extra.setdefault("prices", {})["SeatGeek"] = {
                    "min": lo, "max": hi or lo, "cur": "USD", "url": hits[0].get("url", ""),
                }
        except (json.JSONDecodeError, IndexError, AttributeError):
            continue


def _enrich_ticketmaster(events: list[Event]) -> None:
    """Face-value/primary prices from Ticketmaster's official Discovery API.

    Get a free key at https://developer.ticketmaster.com then:
        export TICKETMASTER_API_KEY=your_key
    Prices come back in the event's local currency (GBP/EUR).
    """
    key = os.environ.get("TICKETMASTER_API_KEY")
    if not key:
        print("  (set TICKETMASTER_API_KEY for primary-sale prices — free key at developer.ticketmaster.com)")
        return
    for ev in events[:PRICE_ENRICH_CAP]:
        url = (f"https://app.ticketmaster.com/discovery/v2/events.json"
               f"?apikey={key}&keyword={quote(ev.title)}&size=1")
        raw = fetch(url)
        if not raw:
            continue
        try:
            hits = (json.loads(raw).get("_embedded") or {}).get("events") or []
            pr = (hits[0].get("priceRanges") or [{}])[0]
            if pr.get("min"):
                ev.extra.setdefault("prices", {})["Ticketmaster"] = {
                    "min": pr["min"], "max": pr.get("max", pr["min"]),
                    "cur": pr.get("currency", "EUR"), "url": hits[0].get("url", ""),
                }
        except (json.JSONDecodeError, IndexError, AttributeError):
            continue


def scrape() -> list[Event]:
    start = date.today()
    end = start + timedelta(days=WINDOW_DAYS)
    dates = f"{start:%Y%m%d}-{end:%Y%m%d}"

    events: list[Event] = []
    for code, label in LEAGUES:
        url = (
            f"https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/"
            f"scoreboard?dates={dates}&limit=200"
        )
        print(f"  Football ({label}): {url}")
        raw = fetch(url)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            print(f"  ! {label}: unexpected non-JSON response")
            continue
        found = _parse_scoreboard(payload, label)
        print(f"    -> {len(found)} fixtures")
        events += found

    _enrich_seatgeek(events)
    _enrich_ticketmaster(events)
    return events
