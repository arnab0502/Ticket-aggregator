"""Scraper registry.

To add a new source: create a module in this package exposing
`scrape() -> list[Event]`, then add it to SCRAPERS below.
"""

from . import allevents, eventz

SCRAPERS = {
    "AllEvents": allevents.scrape,
    "Eventz": eventz.scrape,
}
