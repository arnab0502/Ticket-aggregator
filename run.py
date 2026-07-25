#!/usr/bin/env python3
"""Entry point: scrape all sources -> dedupe -> data/events.json + dashboard.html

Usage:
    python run.py              # scrape live and rebuild the dashboard
    python run.py --offline    # rebuild dashboard from existing data/events.json
"""

import json
import os
import sys

from aggregator.env import load_dotenv
from aggregator.dedupe import assign_groups
from aggregator.dashboard import generate

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(ROOT, "data", "events.json")
DASHBOARD_PATH = os.path.join(ROOT, "dashboard.html")


# Some sites (Eventbrite, BookMyShow) block GitHub Actions' shared runner
# IPs specifically — the scraper itself works fine, it just comes back with
# 0 results there every time. Without a fallback, each 3-hourly automated
# run would silently wipe that source's events from data/events.json even
# though nothing about the source actually changed. Predicate per scraper
# name so we know which stale events to keep when a scrape comes back
# empty. Movies/USMovies both use source "Wikipedia" (India vs US movie
# calendars) so they're split by city instead.
SOURCE_MATCH = {
    "AllEvents": lambda e: e["source"] == "AllEvents",
    "Eventz": lambda e: e["source"] == "Eventz",
    "Movies": lambda e: e["source"] == "Wikipedia" and e["city"] == "All India",
    "Football": lambda e: e["source"] == "ESPN",
    "BookMyShow": lambda e: e["source"] == "BookMyShow",
    "Eventbrite": lambda e: e["source"] == "Eventbrite",
    "USMovies": lambda e: e["source"] == "Wikipedia" and e["city"] == "All USA",
}


def scrape_all(existing: list[dict]) -> list[dict]:
    from scrapers import SCRAPERS

    events = []
    for name, scrape in SCRAPERS.items():
        print(f"Scraping {name}…")
        stale = [e for e in existing if SOURCE_MATCH[name](e)]
        try:
            found = scrape()
            print(f"  -> {len(found)} events")
            if found:
                events += [e.to_dict() for e in found]
            elif stale:
                print(f"  !! 0 events (likely blocked) — keeping {len(stale)} from the last successful scrape")
                events += stale
        except Exception as exc:  # one broken source shouldn't kill the run
            print(f"  !! {name} failed: {exc}")
            if stale:
                print(f"  keeping {len(stale)} events from the last successful scrape")
                events += stale
    return events


def main() -> int:
    load_dotenv(os.path.join(ROOT, ".env"))
    if "--offline" in sys.argv:
        if not os.path.exists(DATA_PATH):
            print("No data/events.json yet — run without --offline first.")
            return 1
        with open(DATA_PATH, encoding="utf-8") as f:
            events = json.load(f)
        print(f"Loaded {len(events)} events from {DATA_PATH}")
    else:
        existing = []
        if os.path.exists(DATA_PATH):
            with open(DATA_PATH, encoding="utf-8") as f:
                existing = json.load(f)
        events = scrape_all(existing)
        if not events:
            print("No events scraped (network blocked or site layouts changed).")
            return 1
        os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(events)} events -> {DATA_PATH}")

    assign_groups(events)

    # Enrich: events in a cross-source group missing a price are worth a
    # detail-page fetch so the price comparison actually has numbers.
    if "--offline" not in sys.argv:
        from scrapers.allevents import fetch_price

        candidates = [
            e for e in events
            if e["multi_source"] and e["price_min"] is None and e["source"] == "AllEvents"
        ][:15]  # cap so a big run stays fast
        if candidates:
            print(f"Enriching prices for {len(candidates)} cross-listed events…")
        for e in candidates:
            lo, hi = fetch_price(e["url"])
            if lo is not None:
                e["price_min"], e["price_max"] = lo, hi
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)

    dupes = sum(1 for e in events if e["multi_source"])
    generate(events, DASHBOARD_PATH)
    print(f"Dashboard -> {DASHBOARD_PATH} ({len(events)} events, {dupes} on multiple sites)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
