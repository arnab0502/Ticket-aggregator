# 🎟️ Global Events Aggregator

Aggregates shows and events (comedy, kids, nightlife, markets, movies,
football and more) from Indian, US and international listing sites into
one filterable dashboard, and flags events listed on multiple platforms
so you can compare prices.

**Output:** a single self-contained `dashboard.html` you can open in any
browser or host on GitHub Pages / Netlify.

## Coverage — what's actually scraped, and what isn't

Being upfront about this matters: an aggregator is only useful if you know
where its blind spots are. Here's every source, exactly what it covers, and
why it's scoped the way it is.

| Source | Region | Categories | Notes |
|---|---|---|---|
| AllEvents | Bangalore, Mumbai, Delhi NCR, Hyderabad | Comedy, Kids, Nightlife | Indexed directly (schema.org JSON-LD) |
| Eventz | Bangalore, Mumbai, Delhi NCR, Hyderabad | Comedy, Kids | Indexed directly |
| Eventbrite | Sacramento, San Francisco, NYC, Chicago | Comedy, Kids, Nightlife, Markets | Indexed directly (same JSON-LD technique as AllEvents) |
| Movies (Wikipedia) | India | Movies (Hindi releases) | Release calendar, not a booking source — see below |
| USMovies (Wikipedia) | US | Movies (all wide theatrical releases, incl. major non-English/int'l titles distributed in the US) | Same idea, US release calendar |
| Football (ESPN API) | Global | EPL, Bundesliga, La Liga, Ligue 1, ISL | Not city-scoped — fixtures show regardless of which city/region filter is selected, since a match isn't tied to one city the way a comedy show is |
| BookMyShow | Bangalore, Mumbai, Delhi NCR, Hyderabad | Best-effort | Blocked by bot detection most runs; still gets a movie booking chip regardless |

**Cities are a scope choice, not a technical ceiling.** Both the India and
US city lists are short by design — same 4-city pattern on both sides —
not because the underlying sites only have events in those cities. Widening
either list is a config change in `scrapers/allevents.py` /
`scrapers/eventz.py` / `scrapers/bookmyshow.py` (India) or
`scrapers/eventbrite.py` (US); say the word and I'll add cities.

**Movies are release-calendar based, not per-cinema.** `movies.py` and
`usmovies.py` don't scrape "what's showing at cinema X today" — they scrape
Wikipedia's release-schedule tables (Hindi films for India, all American
films for the US) and keep anything released in the last 30 days or opening
in the next 120. That window matters: a movie that already released stays
visible for a month (so it doesn't vanish from the dashboard while it's
still actually in theaters), and pulling from the *American* films list
means big global tentpoles (Marvel, Nolan, Pixar, etc.) show up even though
they're not "Hindi films" — those get **both** India and US booking chips
(BookMyShow/District + Fandango/AMC), since day-and-date global releases are
genuinely bookable on either, unlike a purely regional release.

**Football has its own tab**, not just a category filter — the dashboard
now has two top-level tabs, "🎫 Events" and "⚽ Football". Football used to
be a category pill mixed into the same city-filtered grid as everything
else, and its city field doubled as the league name (EPL/Bundesliga/etc.),
which meant filtering by a specific city hid every match — a real bug.
Now Football is fully separate: its own tab, with its own location filter
built from each match's actual stadium city (parsed from the venue string),
completely independent of the Events tab's city/region filter.

**Every card's chips should deep-link to the actual listing, not a
homepage.** This was a real bug for Eventz specifically: its scraper parsed
visible page text for title/venue/date/price but never captured each card's
underlying link, so every Eventz-sourced card pointed at the shared city
listing page instead of its own event page. Fixed — Eventz cards now link
to their real `eventz.co.in/events-list/<slug>` page. Similarly, the
movie booking chips (BookMyShow/District/Fandango/AMC) used to be static
homepage links; District and Fandango now deep-link to a real, verified
title search (`/search?q=<title>`, confirmed against the live sites to
return actual results, not an empty state) — BookMyShow and AMC don't have
a working plain-URL search (both return 404/403 respectively on every
pattern tried), so those two stay as honest browse-page links rather than
a search URL that would silently break.

**Known real limitation: only the first page per city/category is
scraped**, for both AllEvents and Eventbrite — both sites paginate
(confirmed: Eventbrite's `?page=2` returns a completely different set of
20 events, zero overlap with page 1), so there's more content on these
sites than currently shown. Not fixed yet — flag it if you want pagination
added; it's a moderate scope increase (more requests per run, longer
scrape time) but technically straightforward for both sources.

If something big is still missing after reading this table, that's a gap
worth closing, not an inherent limit of the approach — flag it.

## Quick start

```bash
pip install -r requirements.txt
python run.py            # scrape live, then open dashboard.html
python run.py --offline  # rebuild dashboard from data/events.json without scraping
python tests/test_pipeline.py   # run the offline test suite
```

The repo ships with a sample `data/events.json`, so `--offline` works
immediately after cloning.

**One-off refresh:** run `python run.py`, then reload `dashboard.html` in
your browser.

**Live/auto-refreshing dashboard:** run `python serve.py` instead. It opens
the dashboard instantly from cached data, then re-scrapes in the background
on a timer (every 20 min by default — `--interval <seconds>` to change it).
Each source updates the page as soon as it finishes, and the open browser
tab auto-reloads whenever new data lands — no manual re-run needed. Leave
it running in a terminal; `Ctrl+C` to stop.

```bash
python serve.py                     # http://127.0.0.1:8000, scrape every 20 min
python serve.py --interval 600      # every 10 min
python serve.py --port 8080 --no-browser
```

## How it works

```
run.py                    one-off entry point: scrape → dedupe → dashboard
serve.py                  live server: instant cached load, background re-scrape, auto-reload
├── scrapers/
│   ├── base.py           Event model, polite rate-limited fetch, price parsing
│   ├── allevents.py      parses schema.org JSON-LD from allevents.in (India)
│   ├── eventz.py         defensive HTML parsing of eventz.co.in (India)
│   ├── eventbrite.py     parses schema.org JSON-LD from eventbrite.com (US)
│   ├── movies.py         upcoming Hindi film releases from Wikipedia
│   ├── usmovies.py       upcoming US wide releases from Wikipedia
│   ├── football.py       EPL/Bundesliga/LaLiga/Ligue1/ISL fixtures via ESPN API (global, not city-scoped)
│   ├── bookmyshow.py     best-effort (BMS blocks most scraping)
│   └── __init__.py       SCRAPERS registry
├── aggregator/
│   ├── env.py            tiny .env loader shared by run.py / serve.py
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
re-scrapes every 3 hours and commits the refreshed `dashboard.html`. Enable
**Settings → Pages → Deploy from branch → main** to host it at
`https://<you>.github.io/ticket-aggregator/dashboard.html`.

**Keep the repo public** so those Actions runs stay free (unlimited minutes
on public repos; private repos get 2,000 free min/month, and a run every 3
hours can get close to that). `.env` is already gitignored, so no API keys
are exposed by going public.

### Hosting on Netlify instead of GitHub Pages

Netlify only serves static files — there's no server to run `serve.py`'s
background scraper there. Freshness instead comes from the same GitHub
Actions cron job rebuilding `dashboard.html` every 3 hours and pushing it;
Netlify just redeploys whenever that push lands:

1. Push this repo to GitHub (public, per above).
2. In Netlify: **Add new site → Import an existing project → GitHub**, pick
   the repo.
3. Deploy — build command and publish directory come from `netlify.toml`
   (already in the repo): no build step, publishes the repo root, and
   redirects `/` to `/dashboard.html` (Netlify looks for `index.html` at
   the root by default, and there isn't one, so without this redirect the
   site's root URL would 404).
4. Netlify auto-redeploys on every push, including the Actions bot's scrape
   commits — so the hosted page refreshes itself every ~3 hours without you
   touching anything.

This is "auto-refreshing on a schedule," not "live per visit" — a visitor
always sees the latest completed scrape, not one triggered by their own
page load. Skyscanner-style true per-visit live scraping isn't practical on
static hosting for scrapers this heavy (and would also make you look like
a bot to the ticketing sites much faster, since Netlify's cloud IPs are
shared and already flagged by Cloudflare/Akamai far more than a home IP).

## Known limitations

- **BookMyShow, District, StubHub, viagogo and Ticketmaster actively block
  scrapers** (Cloudflare / Akamai bot detection). Football and movie cards
  work around this with pre-built search links and (optionally) official
  free APIs (SeatGeek, Ticketmaster) rather than scraping.
- **Eventbrite listing pages don't expose ticket prices** in their JSON-LD
  (unlike AllEvents, which sometimes does) — US event cards from Eventbrite
  show "See listing" rather than a price until you open the chip. No
  enrichment step exists for this yet (AllEvents has one; Eventbrite doesn't).
- **City/region coverage is intentionally narrow (4 cities per side)**, not
  a hard limit of the scraping approach — see the coverage table above.
- Prices and availability change daily; every card links to the live
  booking page, which is the source of truth.
- Be respectful: the scraper rate-limits itself (1 request / 1.5 s). Check
  each site's `robots.txt` and terms before adding aggressive scraping.
