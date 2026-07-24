"""Scraper registry.

To add a new source: create a module in this package exposing
`scrape() -> list[Event]`, then add it to SCRAPERS below.
"""

from . import allevents, bookmyshow, eventbrite, eventz, football, movies, usmovies

SCRAPERS = {
    "AllEvents": allevents.scrape,
    "Eventz": eventz.scrape,
    "Movies": movies.scrape,
    "Football": football.scrape,
    "BookMyShow": bookmyshow.scrape,
    "Eventbrite": eventbrite.scrape,
    "USMovies": usmovies.scrape,
}
