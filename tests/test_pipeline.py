"""Offline tests: parser, dedupe, and dashboard generation.

Run with:  python -m pytest tests/  (or just: python tests/test_pipeline.py)
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scrapers.allevents import _iter_jsonld_events, _event_from_jsonld
from scrapers.base import parse_prices
from aggregator.dedupe import assign_groups
from aggregator.dashboard import generate

FIXTURE_HTML = """
<html><head>
<script type="application/ld+json">
[{"@type":"Event","name":"Test Comedy Night","url":"https://allevents.in/e/1",
  "startDate":"2026-08-01T20:00:00+05:30",
  "location":{"@type":"Place","name":"Comedy Club BLR"},
  "offers":{"@type":"Offer","price":"499","priceCurrency":"INR"}}]
</script>
</head><body></body></html>
"""


def test_jsonld_parsing():
    objs = list(_iter_jsonld_events(FIXTURE_HTML))
    assert len(objs) == 1, f"expected 1 JSON-LD event, got {len(objs)}"
    ev = _event_from_jsonld(objs[0], "Bangalore", "Comedy")
    assert ev.title == "Test Comedy Night"
    assert ev.venue == "Comedy Club BLR"
    assert ev.price_min == 499.0
    print("ok: JSON-LD parsing")


def test_price_parsing():
    assert parse_prices("Tickets from ₹1,299 and Rs 499") == [1299.0, 499.0]
    print("ok: price parsing")


def test_dedupe_and_dashboard():
    events = [
        {"title": "Shashi Dhiman Live", "city": "Bangalore", "category": "Comedy",
         "source": "District", "url": "https://a/1", "date": "2026-08-02T19:00:00",
         "venue": "V1", "price_min": 299.0, "price_max": 299.0, "currency": "INR",
         "image": "", "extra": {}},
        {"title": "Shashi Dhiman - Live Standup Show", "city": "Bangalore", "category": "Comedy",
         "source": "Eventz", "url": "https://b/1", "date": "2026-08-02T19:00:00",
         "venue": "V1", "price_min": 499.0, "price_max": 499.0, "currency": "INR",
         "image": "", "extra": {}},
        {"title": "Magic Mania for Kids", "city": "Delhi NCR", "category": "Kids",
         "source": "AllEvents", "url": "https://c/1", "date": "2026-08-05T11:00:00",
         "venue": "V2", "price_min": 350.0, "price_max": 350.0, "currency": "INR",
         "image": "", "extra": {}},
    ]
    assign_groups(events)
    assert events[0]["group_id"] == events[1]["group_id"], "duplicates not grouped"
    assert events[0]["multi_source"] and events[1]["multi_source"]
    assert not events[2]["multi_source"]

    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "dash.html")
        generate(events, out)
        html = open(out, encoding="utf-8").read()
        assert "Shashi Dhiman Live" in html
        assert "Global Events" in html
        assert "PRICE COMPARE" in html  # merged card with comparison box
    print("ok: dedupe + dashboard generation")


EVENTZ_FIXTURE = """
<html><body>
<div class="card">
<a href="https://www.eventz.co.in/events-list/out-of-order-ft-shashi-dhiman"><img src="a.jpg"></a>
<span>₹499</span><span>Out Of Order ft.Shashi Dhiman</span>
<span>The Comedy Theatre - Indiranagar, Bangalore</span>
<span>Saturday, 18 July 2026</span><span>Comedy Shows</span>
</div>
<div class="card">
<a href="https://www.eventz.co.in/events-list/talking-to-myself"><img src="b.jpg"></a>
<span>₹199</span><span>Talking to Myself by Shrikant Mandlik</span>
<span>TAG Comedy Club, Bengaluru</span>
<span>Saturday, 18 July 2026</span><span>Comedy Shows</span>
</div>
</body></html>
"""

MOVIES_FIXTURE = """
<table class="wikitable">
<tr><th>Opening</th><th>Title</th></tr>
<tr><td rowspan="2"><b>J U L</b></td><td rowspan="1">25</td>
    <td><i><a href="/wiki/Test_Film">Test Film</a></i></td><td>Someone</td></tr>
<tr><td rowspan="1">31</td><td><i>Second Film</i></td><td>Someone Else</td></tr>
</table>
"""


def test_eventz_parsing():
    from scrapers.eventz import _parse_listing
    evs = _parse_listing(EVENTZ_FIXTURE, "https://x", "Bangalore", "Comedy")
    assert len(evs) == 2, f"expected 2 events, got {[e.title for e in evs]}"
    assert evs[0].title == "Out Of Order ft.Shashi Dhiman"
    assert evs[0].price_min == 499.0
    assert evs[0].date.startswith("2026-07-18")
    # each event must link to its own detail page, not the shared listing page
    assert evs[0].url == "https://www.eventz.co.in/events-list/out-of-order-ft-shashi-dhiman"
    assert evs[1].url == "https://www.eventz.co.in/events-list/talking-to-myself"
    assert evs[1].venue == "TAG Comedy Club, Bengaluru"
    print("ok: eventz parsing")


def test_movies_parsing():
    from scrapers.movies import _parse_year_page
    evs = _parse_year_page(MOVIES_FIXTURE, 2026)
    titles = {e.title for e in evs}
    assert "Test Film" in titles and "Second Film" in titles, titles
    by_title = {e.title: e for e in evs}
    assert by_title["Test Film"].date.startswith("2026-07-25")
    assert by_title["Test Film"].url == "https://en.wikipedia.org/wiki/Test_Film"
    assert by_title["Second Film"].date.startswith("2026-07-31")
    print("ok: movies parsing")


ESPN_FIXTURE = {
    "events": [{
        "name": "Chelsea at Arsenal",
        "date": "2026-08-15T14:00Z",
        "links": [{"href": "https://www.espn.in/football/match/_/gameId/1"}],
        "competitions": [{
            "venue": {"fullName": "Emirates Stadium", "address": {"city": "London"}},
            "competitors": [
                {"homeAway": "home", "team": {"displayName": "Arsenal"}},
                {"homeAway": "away", "team": {"displayName": "Chelsea"}},
            ],
        }],
    }],
}


def test_football_parsing_and_chips():
    from scrapers.football import _parse_scoreboard
    from aggregator.dashboard import _build_cards
    evs = _parse_scoreboard(ESPN_FIXTURE, "EPL")
    assert len(evs) == 1
    ev = evs[0]
    assert ev.title == "Arsenal vs Chelsea"
    assert ev.venue == "Emirates Stadium, London"
    assert ev.extra["official_url"].startswith("https://www.arsenal.com")

    d = ev.to_dict()
    d["group_id"], d["multi_source"] = 0, False
    card = _build_cards([d])[0]
    chips = {s["p"] for s in card["srcs"]}
    assert {"Official", "Ticketmaster", "StubHub", "viagogo", "SeatGeek"} <= chips, chips
    stub = next(s for s in card["srcs"] if s["p"] == "StubHub")
    assert "stubhub.com" in stub["u"] and "Arsenal" in stub["u"]
    assert card["cmpt"] == "Ticket price comparison"
    assert "Face value (typical)" in card["cmp"] and "£30" in card["cmp"]
    print("ok: football parsing + ticket chips")


def test_football_live_prices():
    from aggregator.dashboard import _football_srcs
    extra = {
        "official_url": "https://www.arsenal.com/tickets",
        "prices": {
            "SeatGeek": {"min": 95.0, "max": 450.0, "cur": "USD", "url": "https://seatgeek.com/e/1"},
            "Ticketmaster": {"min": 40.0, "max": 90.0, "cur": "GBP", "url": "https://tm.uk/e/1"},
        },
    }
    srcs, cmp_html = _football_srcs("Arsenal vs Chelsea", "EPL", extra)
    sg = next(s for s in srcs if s["p"] == "SeatGeek")
    assert sg["pmin"] == 95.0 and sg["cur"] == "$" and sg["u"] == "https://seatgeek.com/e/1"
    tm = next(s for s in srcs if s["p"] == "Ticketmaster")
    assert tm["pmin"] == 40.0 and tm["cur"] == "£"
    assert "SeatGeek (live)" in cmp_html and "$95–$450" in cmp_html
    assert "Ticketmaster (live)" in cmp_html and "£40–£90" in cmp_html
    print("ok: football live price rows")


def test_isl_chips():
    from aggregator.dashboard import _football_srcs
    srcs, guide = _football_srcs("Bengaluru FC vs Kerala Blasters", "ISL", {})
    chips = {s["p"] for s in srcs}
    assert {"BookMyShow", "District"} <= chips, chips
    assert "Paytm Insider" not in chips  # insider.in now redirects to district.in — same platform
    assert "BookMyShow" in guide
    print("ok: ISL ticket chips")


def test_containment_dedupe():
    from aggregator.dedupe import normalize, similar
    assert similar(normalize("Out Of Order ft.Shashi Dhiman"), normalize("Shashi Dhiman Live"))
    assert not similar(normalize("Rahul Dua Live"), normalize("Kunal Kamra Live"))
    print("ok: containment dedupe")


if __name__ == "__main__":
    test_jsonld_parsing()
    test_price_parsing()
    test_dedupe_and_dashboard()
    test_eventz_parsing()
    test_movies_parsing()
    test_football_parsing_and_chips()
    test_football_live_prices()
    test_isl_chips()
    test_containment_dedupe()
    print("All tests passed.")
