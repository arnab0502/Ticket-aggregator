# 🎟️ India Events Aggregator

Aggregates shows and events (comedy, kids, nightlife, and more) from Indian
listing sites into one filterable dashboard, and flags events listed on
multiple platforms so you can compare prices.

**Sources:** AllEvents, Eventz — more can be added (see below).
**Output:** a single self-contained `dashboard.html` you can open in any
browser or host on GitHub Pages.

## Quick start

```bash
pip install -r requirements.txt
python run.py            # scrape live, then open dashboard.html
python run.py --offline  # rebuild dashboard from data/events.json without scraping
python tests/test_pipeline.py   # run the offline test suite
```

The repo ships with a small sample `data/events.json`, so `--offline` works
immediately after cloning.

## How it works

```
run.py                    entry point: scrape → dedupe → dashboard
├── scrapers/
│   ├── base.py           Event model, polite rate-limited fetch, price parsing
│   ├── allevents.py      parses schema.org JSON-LD from allevents.in
│   ├── eventz.py         defensive HTML parsing of eventz.co.in
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

- **BookMyShow and District actively block scrapers** (Cloudflare / bot
  detection). Plain HTTP scraping won't work for them; options are their
  official partner APIs, or a headless browser (Playwright) — PRs welcome.
- Prices and availability change daily; every card links to the live
  booking page, which is the source of truth.
- Be respectful: the scraper rate-limits itself (1 request / 1.5 s). Check
  each site's `robots.txt` and terms before adding aggressive scraping.
