#!/usr/bin/env python3
"""Entry point: scrape all sources -> dedupe -> data/events.json + dashboard.html

Usage:
    python run.py              # scrape live and rebuild the dashboard
    python run.py --offline    # rebuild dashboard from existing data/events.json
"""

import json
import os
import sys


def _load_dotenv(path: str) -> None:
    """Tiny .env loader (KEY=value lines) so API keys don't need exports."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))

from aggregator.dedupe import assign_groups
from aggregator.dashboard import generate

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(ROOT, "data", "events.json")
DASHBOARD_PATH = os.path.join(ROOT, "dashboard.html")


def scrape_all() -> list[dict]:
    from scrapers import SCRAPERS

    events = []
    for name, scrape in SCRAPERS.items():
        print(f"Scraping {name}…")
        try:
            found = scrape()
            print(f"  -> {len(found)} events")
            events += [e.to_dict() for e in found]
        except Exception as exc:  # one broken source shouldn't kill the run
            print(f"  !! {name} failed: {exc}")
    return events


def main() -> int:
    _load_dotenv(os.path.join(ROOT, ".env"))
    if "--offline" in sys.argv:
        if not os.path.exists(DATA_PATH):
            print("No data/events.json yet — run without --offline first.")
            return 1
        with open(DATA_PATH, encoding="utf-8") as f:
            events = json.load(f)
        print(f"Loaded {len(events)} events from {DATA_PATH}")
    else:
        events = scrape_all()
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
