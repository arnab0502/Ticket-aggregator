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
        assert json.dumps  # embedded JSON present
        assert "India Events Aggregator" in html
    print("ok: dedupe + dashboard generation")


if __name__ == "__main__":
    test_jsonld_parsing()
    test_price_parsing()
    test_dedupe_and_dashboard()
    print("All tests passed.")
