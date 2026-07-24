#!/usr/bin/env python3
"""Local live dashboard: serves dashboard.html immediately from cache, then
re-scrapes in the background on a timer. Each source updates the page as
soon as it finishes (not all-or-nothing), and any browser tab left open
auto-reloads when new data lands — no manual re-run needed.

Usage:
    python serve.py                      # scrape every 20 min, open browser
    python serve.py --interval 600        # scrape every 10 min
    python serve.py --port 8080 --no-browser
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import threading
import time
import webbrowser

from aggregator.env import load_dotenv
from aggregator.dedupe import assign_groups
from aggregator.dashboard import generate

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(ROOT, "data", "events.json")
DASHBOARD_PATH = os.path.join(ROOT, "dashboard.html")

_lock = threading.Lock()
_status = {"version": 0.0, "scraping": False, "current": None, "last_run": None}


def _load_data() -> list[dict]:
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_data(events: list[dict]) -> None:
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


def _regenerate(events: list[dict]) -> None:
    """Rebuild dashboard.html and bump the version an open tab polls for."""
    assign_groups(events)
    version = time.time()
    tmp = DASHBOARD_PATH + ".tmp"
    generate(events, tmp, live=True, version=version)
    os.replace(tmp, DASHBOARD_PATH)  # atomic — never serves a half-written file
    with _lock:
        _status["version"] = version


def _scrape_pass() -> None:
    from scrapers import SCRAPERS

    working = _load_data()
    for name, scrape in SCRAPERS.items():
        with _lock:
            _status["scraping"] = True
            _status["current"] = name
        print(f"Scraping {name}…")
        try:
            found = scrape()
            new_events = [e.to_dict() for e in found]
            print(f"  -> {len(new_events)} events")
        except Exception as exc:  # one broken source shouldn't kill the run
            print(f"  !! {name} failed: {exc}")
            continue
        # Swap in this source's fresh results and push the update right
        # away — the open dashboard fills in per-source, like a metasearch
        # page filling in prices as each provider responds.
        working = [e for e in working if e["source"] != name] + new_events
        _regenerate(working)

    if working:
        from scrapers.allevents import fetch_price

        candidates = [
            e for e in working
            if e["multi_source"] and e["price_min"] is None and e["source"] == "AllEvents"
        ][:15]
        if candidates:
            print(f"Enriching prices for {len(candidates)} cross-listed events…")
        for e in candidates:
            lo, hi = fetch_price(e["url"])
            if lo is not None:
                e["price_min"], e["price_max"] = lo, hi
        _regenerate(working)
        _save_data(working)

    with _lock:
        _status["scraping"] = False
        _status["current"] = None
        _status["last_run"] = time.time()
    dupes = sum(1 for e in working if e.get("multi_source"))
    print(f"Scrape pass done — {len(working)} events, {dupes} on multiple sites")


def _scrape_loop(interval: int) -> None:
    while True:
        try:
            _scrape_pass()
        except Exception as exc:
            print(f"!! scrape pass crashed: {exc}")
        time.sleep(interval)


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/status"):
            with _lock:
                body = json.dumps(_status).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/":
            self.path = "/dashboard.html"
        return super().do_GET()

    def log_message(self, fmt, *args):
        pass  # scraper progress lines are the useful console signal


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--interval", type=int, default=1200, help="seconds between scrape passes (default 1200 = 20 min)")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    load_dotenv(os.path.join(ROOT, ".env"))

    # Instant load from whatever's cached, so the tab never sits on a blank
    # or static page waiting for the first scrape to finish.
    _regenerate(_load_data())

    threading.Thread(target=_scrape_loop, args=(args.interval,), daemon=True).start()

    handler = functools.partial(Handler, directory=ROOT)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Serving live dashboard at {url}")
    print(f"Re-scraping every {args.interval}s in the background — leave this running, keep the tab open.")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
