# 🎟️ India Events Aggregator

Aggregates shows and events (comedy, kids, nightlife, football and more) from
Indian and international listing sites into one filterable dashboard, and
flags events listed on multiple platforms so you can compare prices.

**Sources:** AllEvents, Eventz, Wikipedia (movie release calendars), ESPN
(football fixtures), BookMyShow (best-effort) — plus ticket marketplace
links (Official club sites, Ticketmaster, StubHub, viagogo, SeatGeek) for
football matches.
**Output:** a single self-contained `dashboard.html` you can open in any
browser or host on GitHub Pages.

## Quick start

```bash
pip install -r requirements.txt
python run.py            # scrape live, then open dashboard.html
python run.py --offline  # rebuild dashboard from data/events.json without scraping
python tests/test_pipeline.py   # run the offline test suite
```

The repo ships with a sample `data/events.json`, so `--offline` works
immediately after cloning.

**To refresh the dashboard:** run `python run.py`, then reload
`dashboard.html` in your browser. That's the whole loop — the script
re-scrapes every source and regenerates the HTML file each time.

## How it works

```
run.py                    entry point: scrape → dedupe → dashboard
├── scrapers/
│   ├── base.py           Event model, polite rate-limited fetch, price parsing
│   ├── allevents.py      parses schema.org JSON-LD from allevents.in
│   ├── eventz.py         defensive HTML parsing of eventz.co.in
│   ├── movies.py         upcoming Hindi film releases from Wikipedia
│   ├── football.py       EPL/Bundesliga/LaLiga/Ligue1/ISL fixtures via ESPN API
│   ├── bookmyshow.py     best-effort (BMS blocks most scraping)
│   └── __init__.py       SCRAPERS registry
├── aggregator/
│   ├── dedupe.py         fuzzy title matching per city → duplicate groups
│   └── dashboard.py      renders dashboard.html with embedded JSON data
├── data/events.json      last scrape result
└── dashboard.html        generated dashboard (filter / search / sort / price-compare)
```

## Adding a new source

1. Create `scrapers/mysite.py` exposing `scrape() -> list[Event]`.
2. Register it in `scrapers/__init__.py`:

```python
from . import mysite
SCRAPERS["MySite"] = mysite.scrape
```

That's it — dedupe and the dashboard pick it up automatically.

## Football: live ticket prices (optional, free API keys)

Football fixtures (EPL, Bundesliga, La Liga, Ligue 1, ISL) come from
ESPN's public API with no key needed. Ticket marketplaces block scraping,
so match cards always show a typical face-value range plus pre-built
search links (Official club office, Ticketmaster, StubHub, viagogo,
SeatGeek). For **live** prices in the comparison box, copy `.env.example`
to `.env` and add free official API keys:

```bash
cp .env.example .env
# then edit .env and paste in:
SEATGEEK_CLIENT_ID=...     # https://seatgeek.com/account/develop (resale, USD)
TICKETMASTER_API_KEY=...   # https://developer.ticketmaster.com (primary, GBP/EUR)
python run.py
```

StubHub's API is partner-only, so StubHub chips stay search links.

## Collaborating via GitHub

```bash
# one-time, from this folder
git init
git add .
git commit -m "Initial commit: events aggregator"
# create an empty repo on github.com, then:
git remote add origin https://github.com/<you>/ticket-aggregator.git
git branch -M main
git push -u origin main
```

Then add teammates under **Settings → Collaborators** on GitHub. Suggested
workflow: branch → pull request → review → merge.

A GitHub Actions workflow (`.github/workflows/scrape.yml`) is included that
re-scrapes daily and commits the refreshed dashboard. Enable **Settings →
Pages → Deploy from branch → main** to host `dashboard.html` at
`https://<you>.github.io/ticket-aggregator/dashboard.html`.

## Known limitations

- **BookMyShow, District, StubHub, viagogo and Ticketmaster actively block
  scrapers** (Cloudflare / Akamai bot detection). Football and movie cards
  work around this with pre-built search links and (optionally) official
  free APIs (SeatGeek, Ticketmaster) rather than scraping.
- Prices and availability change daily; every card links to the live
  booking page, which is the source of truth.
- Be respectful: the scraper rate-limits itself (1 request / 1.5 s). Check
  each site's `robots.txt` and terms before adding aggressive scraping.
