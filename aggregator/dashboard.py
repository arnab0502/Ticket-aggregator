"""Generates dashboard.html from a list of event dicts.

Design ported from the original "India Events Dashboard" snapshot: dark
theme, city/category pill filters, per-category badges, colored source
chips, and a price-comparison box on cards found on 2+ platforms. Now
spans India and the US, so the city filter is really a "region" filter.

Events sharing a group_id (see aggregator.dedupe) are merged into ONE
card listing every platform, with an auto-generated comparison line.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import quote

# Normalize scraper categories to display labels
CATEGORY_LABELS = {
    "Kids": "Kids & Family",
    "Nightlife": "Beer & Nightlife",
    "Music": "Music & Culture",
    "Markets": "Markets & Expos",
}


def _movie_booking_links(title: str, include_us: bool) -> list[dict]:
    """Booking chips for movies: these platforms block scraping but are
    where people actually book, so cards link straight to them.

    Deep-links to a title search where the platform actually supports one
    (verified against the live site): District and Fandango both have a
    working `/search?q=` that returns real results. BookMyShow's search is
    JS/API-driven with no plain crawlable URL (both guessed patterns
    404'd), and AMC blocks automated requests on its search page exactly
    as hard as its plain movies page (403 either way) — both fall back to
    a browse-page link rather than a link that's silently broken.
    """
    q = quote(title)
    links = [
        {"p": "BookMyShow", "u": "https://in.bookmyshow.com/explore/movies"},
        {"p": "District", "u": f"https://www.district.in/search?q={q}"},
    ]
    if include_us:
        links += [
            {"p": "Fandango", "u": f"https://www.fandango.com/search?q={q}"},
            {"p": "AMC Theatres", "u": "https://www.amctheatres.com/movies"},
        ]
    return links

# Ticketmaster localizes per country; pick the right storefront per league.
TICKETMASTER_BY_LEAGUE = {
    "EPL": "https://www.ticketmaster.co.uk/search?q=",
    "Bundesliga": "https://www.ticketmaster.de/search?keyword=",
    "La Liga": "https://www.ticketmaster.es/search?keyword=",
    "Ligue 1": "https://www.ticketmaster.fr/fr/recherche?keyword=",
}


# Typical matchday face-value ranges (2026), shown so the comparison box
# always has a baseline even without live marketplace prices.
LEAGUE_FACE_VALUE = {
    "EPL": "£30–£100",
    "Bundesliga": "€15–€70",
    "La Liga": "€25–€100",
    "Ligue 1": "€15–€80",
    "ISL": "₹200–₹1,500",
}

CUR_SYMBOL = {"USD": "$", "GBP": "£", "EUR": "€", "INR": "₹"}


def _football_srcs(card_title: str, league: str, extra: dict) -> tuple[list[dict], str]:
    """Ticket chips + price-comparison box for a football match card.

    Live prices (extra['prices'], from the SeatGeek / Ticketmaster APIs)
    are shown on chips and as comparison rows; the league's typical
    face-value range is always shown as the baseline row.
    """
    from urllib.parse import quote

    q = quote(card_title)
    live = extra.get("prices") or {}

    def chip(name: str, default_url: str) -> dict:
        p = live.get(name)
        if p:
            return {"p": name, "u": p.get("url") or default_url,
                    "pmin": p["min"], "cur": CUR_SYMBOL.get(p["cur"], "")}
        return {"p": name, "u": default_url, "pmin": None}

    srcs = []
    if extra.get("official_url"):
        srcs.append({"p": "Official", "u": extra["official_url"], "pmin": None})

    if league == "ISL":
        srcs += [
            {"p": "BookMyShow", "u": "https://in.bookmyshow.com/explore/sports", "pmin": None},
            {"p": "District", "u": f"https://www.district.in/search?q={q}", "pmin": None},
            {"p": "Paytm Insider", "u": "https://insider.in/", "pmin": None},
        ]
        guide_tail = "Book direct on BookMyShow / District / Paytm Insider — resale markets rarely list ISL."
    else:
        tm_search = TICKETMASTER_BY_LEAGUE.get(league, "")
        srcs += [
            chip("Ticketmaster", tm_search + q),
            chip("SeatGeek", f"https://seatgeek.com/search?search={q}"),
            {"p": "StubHub", "u": f"https://www.stubhub.com/search?q={q}", "pmin": None},
            {"p": "viagogo", "u": f"https://www.viagogo.com/search?q={q}", "pmin": None},
        ]
        guide_tail = ("Official/Ticketmaster = face value; StubHub / viagogo / SeatGeek = resale, "
                      "usually above face value.")

    # Comparison rows: face-value baseline, then one row PER SOURCE showing
    # either its live price or why there isn't one yet.
    def row(label: str, value: str, cls: str = "na") -> str:
        return (f"<div class='cmprow'><span>{label}</span>"
                f"<span class='{cls}'>{value}</span></div>")

    rows = []
    face = LEAGUE_FACE_VALUE.get(league)
    if face:
        rows.append(row("Face value (typical)", face, "win"))

    def live_or(label: str, fallback: str) -> str:
        p = live.get(label)
        if p:
            sym = CUR_SYMBOL.get(p["cur"], "")
            rng = f"{sym}{int(p['min'])}" + (f"–{sym}{int(p['max'])}" if p["max"] != p["min"] else "")
            return row(f"{label} (live)", rng, "lose")
        return row(label, fallback)

    if league == "ISL":
        rows.append(row("BookMyShow / District / Insider", "~₹200+, open chip"))
    else:
        rows.append(live_or("Ticketmaster", "🔑 free API key → live price"))
        rows.append(live_or("SeatGeek", "🔑 free API key → live price"))
        rows.append(row("StubHub / viagogo", "resale — open chip for live price"))

    guide = "".join(rows) + f"<div class='cmpsum'>{guide_tail}</div>"
    return srcs, guide


def _fmt_price(lo, hi, currency: str = "INR") -> str:
    sym = CUR_SYMBOL.get(currency, "₹")
    f = lambda n: f"{sym}{int(n):,}" if n == int(n) else f"{sym}{n:,}"
    if lo is None:
        return "See listing"
    if hi is None or hi == lo:
        return f(lo)
    return f"{f(lo)}–{f(hi)}"


def _fmt_date(iso: str) -> str:
    if not iso:
        return "Date on listing"
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    txt = d.strftime("%a %d %b")
    if (d.hour, d.minute) != (0, 0):
        hour12 = d.hour % 12 or 12
        txt += f" · {hour12}:{d.minute:02d} {'PM' if d.hour >= 12 else 'AM'}"
    return txt


def _comparison(srcs: list[dict]) -> str | None:
    """Side-by-side price rows, one per platform, cheapest highlighted."""
    if len(srcs) < 2:
        return None
    priced = [s for s in srcs if s.get("pmin") is not None]
    if len(priced) >= 2:
        best = min(s["pmin"] for s in priced)
        rows = []
        for s in sorted(srcs, key=lambda s: (s.get("pmin") is None, s.get("pmin") or 0)):
            if s.get("pmin") is not None:
                cls = "win" if s["pmin"] == best else "lose"
                price = f"<span class='{cls}'>₹{int(s['pmin'])}</span>"
            else:
                price = "<span class='na'>see listing</span>"
            rows.append(f"<div class='cmprow'><span>{s['p']}</span>{price}</div>")
        prices = sorted({s["pmin"] for s in priced})
        cheapest = min(priced, key=lambda s: s["pmin"])["p"]
        summary = (f"<div class='cmpsum'>{cheapest} is ₹{int(prices[-1] - prices[0])} cheaper</div>"
                   if len(prices) > 1 else "<div class='cmpsum'>Same price — book on either</div>")
        return "".join(rows) + summary
    names = " and ".join(s["p"] for s in srcs)
    return f"Cross-listed on {names} — prices differ by platform, compare before booking."


def _build_cards(events: list[dict]) -> list[dict]:
    groups: dict[int, list[dict]] = {}
    for e in events:
        groups.setdefault(e.get("group_id", id(e)), []).append(e)

    cards = []
    for members in groups.values():
        members.sort(key=lambda e: len(e["title"]))
        lead = members[0]
        category = CATEGORY_LABELS.get(lead["category"], lead["category"])
        city = "All cities" if lead["city"] in ("All India", "All USA", "All cities") else lead["city"]
        currency = next((m["currency"] for m in members if m.get("currency")), "INR")

        srcs, seen_src = [], set()
        for m in members:
            if m["source"] not in seen_src:
                srcs.append({"p": m["source"], "u": m["url"], "pmin": m["price_min"]})
                seen_src.add(m["source"])
        if category == "Movies":
            # Hollywood wide releases typically open day-and-date in India too
            # (BookMyShow/District sell tickets for them), so give US-sourced
            # movie cards both regions' booking chips rather than just US ones.
            links = _movie_booking_links(lead["title"], include_us=lead["city"] == "All USA")
            for link in links:
                if link["p"] not in seen_src:
                    srcs.append({**link, "pmin": None})

        prices = [m["price_min"] for m in members if m["price_min"] is not None]
        highs = [m["price_max"] for m in members if m["price_max"] is not None]
        date = min((m["date"] for m in members if m["date"]), default="")
        venue = next((m["venue"] for m in members if m["venue"]), "")

        cmp_title = "Platform comparison"
        ptxt_override = None
        if category == "Football":
            srcs, cmp_line = _football_srcs(lead["title"], city, lead.get("extra") or {})
            cmp_title = "Ticket price comparison"
            live_chips = [s for s in srcs if s.get("pmin") is not None]
            if live_chips:
                cheapest = min(live_chips, key=lambda s: s["pmin"])
                ptxt_override = f"From {cheapest.get('cur', '')}{int(cheapest['pmin'])} ({cheapest['p']})"
            else:
                ptxt_override = "Prices on ticket sites"
        else:
            cmp_line = _comparison(srcs) if len(seen_src) > 1 else None

        cards.append({
            "n": lead["title"],
            "city": city,
            "cat": category,
            "date": (date or "9999")[:10],
            "dtxt": _fmt_date(date),
            "v": venue or ("Cinemas nationwide" if category == "Movies" else city),
            "pmin": min(prices) if prices else None,
            "ptxt": ptxt_override or _fmt_price(min(prices) if prices else None,
                                                max(highs) if highs else None, currency),
            "srcs": srcs,
            "cmp": cmp_line,
            "cmpt": cmp_title,
        })
    cards.sort(key=lambda c: c["date"])
    return cards


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Global Events Dashboard — All Listings, One Place</title>
<style>
  :root{
    --bg:#0f1117; --card:#181b25; --card2:#1f2333; --text:#e8eaf2; --muted:#9aa0b4;
    --accent:#f5a623; --green:#3ecf8e; --red:#ff6b6b; --blue:#5b8def; --purple:#a78bfa; --pink:#f472b6;
    --border:#2a2f42;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--text);padding:24px 20px 60px}
  .wrap{max-width:1200px;margin:0 auto}
  h1{font-size:26px;margin-bottom:4px}
  h1 span{color:var(--accent)}
  .sub{color:var(--muted);font-size:13px;margin-bottom:20px}
  .controls{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px;align-items:center}
  .search{flex:1;min-width:220px;background:var(--card);border:1px solid var(--border);border-radius:10px;padding:10px 14px;color:var(--text);font-size:14px;outline:none}
  .search:focus{border-color:var(--accent)}
  select{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:10px 12px;color:var(--text);font-size:13px;outline:none;cursor:pointer}
  .pills{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px}
  .pill{background:var(--card);border:1px solid var(--border);border-radius:20px;padding:7px 15px;font-size:13px;color:var(--muted);cursor:pointer;user-select:none;transition:.15s}
  .pill:hover{border-color:var(--accent);color:var(--text)}
  .pill.active{background:var(--accent);color:#111;border-color:var(--accent);font-weight:600}
  .pill.cat.active{background:var(--blue);border-color:var(--blue);color:#fff}
  .pill.tab{font-weight:600}
  .pill.tab.active{background:var(--green);border-color:var(--green);color:#111}
  .stats{color:var(--muted);font-size:13px;margin:8px 0 18px}
  .stats b{color:var(--text)}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px}
  .card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:16px;display:flex;flex-direction:column;gap:8px;transition:.15s}
  .card:hover{border-color:#3d4460;transform:translateY(-2px)}
  .row{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
  .title{font-size:15px;font-weight:650;line-height:1.35}
  .badge{font-size:10.5px;font-weight:700;letter-spacing:.4px;padding:3px 8px;border-radius:6px;white-space:nowrap;text-transform:uppercase}
  .b-comedy{background:#3d2f14;color:var(--accent)} .b-movies{background:#3a1a1a;color:var(--red)}
  .b-kids{background:#14332a;color:var(--green)} .b-beer{background:#2a1f3d;color:var(--purple)}
  .b-magic{background:#33142c;color:var(--pink)} .b-music{background:#14243d;color:var(--blue)}
  .b-market{background:#2e2e1a;color:#d4d46a} .b-other{background:#252a3a;color:var(--muted)}
  .b-foot{background:#0f2e33;color:#4dd0e1}
  .meta{color:var(--muted);font-size:12.5px;line-height:1.5}
  .meta .d{color:var(--text);font-weight:600}
  .price{font-size:14px;font-weight:700;color:var(--green)}
  .price.na{color:var(--muted);font-weight:400;font-size:12.5px}
  .srcs{display:flex;flex-wrap:wrap;gap:6px;margin-top:auto;padding-top:8px}
  .src{font-size:11.5px;padding:4px 10px;border-radius:6px;text-decoration:none;font-weight:600;border:1px solid var(--border);color:var(--text)}
  .src:hover{filter:brightness(1.25)}
  .s-allevents{background:#12341f;border-color:#1d5c37} .s-district{background:#2b1d47;border-color:#4c357c}
  .s-eventz{background:#3d2a12;border-color:#6b4a1e} .s-bms{background:#3d1216;border-color:#6b1e26}
  .s-cherishx{background:#3d1230;border-color:#6b1e55} .s-wiki{background:#252a3a;border-color:#3a4158}
  .s-stubhub{background:#3d1a3d;border-color:#6b2e6b} .s-tm{background:#12253d;border-color:#1e426b}
  .s-vg{background:#123d33;border-color:#1e6b59} .s-sg{background:#3d2312;border-color:#6b3e1e}
  .s-official{background:#1a3d1a;border-color:#2e6b2e} .s-insider{background:#2d1240;border-color:#502070}
  .s-espn{background:#3d1216;border-color:#6b1e26}
  .s-eventbrite{background:#3d1f08;border-color:#6b3a12} .s-fandango{background:#1f2e3d;border-color:#355a78}
  .s-amc{background:#2a1f0a;border-color:#4a3712}
  .compare{background:var(--card2);border:1px dashed #4c357c;border-radius:10px;padding:10px 12px;font-size:12.5px;line-height:1.6}
  .compare .t{color:var(--purple);font-weight:700;font-size:11px;letter-spacing:.5px;text-transform:uppercase;margin-bottom:3px}
  .compare .win{color:var(--green);font-weight:700}
  .compare .lose{color:var(--red)}
  .compare .na{color:var(--muted)}
  .cmprow{display:flex;justify-content:space-between;gap:12px;padding:2px 0;border-bottom:1px solid #262b3f}
  .cmprow:last-of-type{border-bottom:none}
  .cmpsum{margin-top:6px;color:var(--muted);font-size:11.5px;font-style:italic}
  .dupbanner{display:inline-block;font-size:10.5px;background:#2b1d47;color:var(--purple);border-radius:6px;padding:3px 8px;font-weight:700;letter-spacing:.3px}
  .note{margin-top:28px;background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px 18px;color:var(--muted);font-size:12.5px;line-height:1.7}
  .note b{color:var(--text)}
  .empty{grid-column:1/-1;text-align:center;color:var(--muted);padding:60px 0;font-size:15px}
</style>
</head>
<body>
<div class="wrap">
  <h1>🎟️ Global Events <span>Dashboard</span></h1>
  <div class="sub">Snapshot: __GENERATED__ · Sources: __SOURCES__ · __COUNT__ listings</div>

  <div class="pills" id="viewTabs"></div>

  <div class="controls">
    <input class="search" id="q" placeholder="Search shows, artists, venues…">
    <select id="src"><option value="">All sources</option></select>
    <select id="sort">
      <option value="date">Sort: Date ↑</option>
      <option value="priceAsc">Sort: Price ↑</option>
      <option value="priceDesc">Sort: Price ↓</option>
    </select>
    <label style="font-size:13px;color:var(--muted);display:flex;align-items:center;gap:6px;cursor:pointer">
      <input type="checkbox" id="dupOnly"> Price-compare only
    </label>
  </div>

  <div class="pills" id="cities"></div>
  <div class="pills" id="cats"></div>
  <div class="pills" id="floc"></div>
  <div class="stats" id="stats"></div>
  <div class="grid" id="grid"></div>

  <div class="note">
    <b>How to read this:</b> Each card shows the event with every platform it was found on — click a source chip to open that listing and book. Cards with a
    <span class="dupbanner">⇄ PRICE COMPARE</span> banner were found on 2+ platforms — the comparison box shows which is cheaper.<br><br>
    <b>Caveats:</b> Prices, dates and availability change fast — always confirm on the booking page. BookMyShow &amp; District block full automated scraping, so their chips are booking links rather than scraped prices; AllEvents, Eventz and Eventbrite are indexed directly, movies come from release calendars (Wikipedia, India and US), football fixtures from ESPN's public API. Movie ticket prices vary by cinema/format (typically ₹150–600 in India; Fandango/AMC pricing varies by market in the US). <b>Football:</b> buy from the club's Official ticket office or Ticketmaster first (face value); StubHub / viagogo / SeatGeek are resale markets — legitimate, but prices float above face value and some clubs restrict resale, so check the club's resale policy. ISL tickets: BookMyShow / District / Paytm Insider. Football lives in its own <b>⚽ Football</b> tab with a location filter based on each match's actual stadium city, separate from the Events city/region filter. Re-run <b>python run.py</b> anytime for a fresh snapshot.
  </div>
</div>

<script>
const EVENTS=__DATA__;

const CITIES=["All",...new Set(EVENTS.filter(e=>e.cat!=="Football").map(e=>e.city).filter(c=>c!=="All cities"))];
const CATS=["All",...new Set(EVENTS.filter(e=>e.cat!=="Football").map(e=>e.cat))];
const catClass={"Comedy":"b-comedy","Movies":"b-movies","Kids & Family":"b-kids","Beer & Nightlife":"b-beer","Magic":"b-magic","Music & Culture":"b-music","Markets & Expos":"b-market","Football":"b-foot"};
const srcClass={"AllEvents":"s-allevents","District":"s-district","Eventz":"s-eventz","BookMyShow":"s-bms","CherishX":"s-cherishx","Wikipedia":"s-wiki","StubHub":"s-stubhub","Ticketmaster":"s-tm","viagogo":"s-vg","SeatGeek":"s-sg","Official":"s-official","Paytm Insider":"s-insider","ESPN":"s-espn","Eventbrite":"s-eventbrite","Fandango":"s-fandango","AMC Theatres":"s-amc"};

// Football's venue string is "<Stadium>, <City>" (see scrapers/football.py) —
// use the part after the last comma as its location, independent of the
// Events tab's city/region filter entirely.
function footballLoc(e){
  const v=e.v||"";
  const i=v.lastIndexOf(",");
  return i>-1?v.slice(i+1).trim():(v||"Unknown");
}
const FOOT_LOCS=["All",...[...new Set(EVENTS.filter(e=>e.cat==="Football").map(footballLoc))].sort()];

let state={view:"events",city:"All",cat:"All",floc:"All",q:"",src:"",sort:"date",dupOnly:false};

const srcSel=document.getElementById("src");
[...new Set(EVENTS.flatMap(e=>e.srcs.map(s=>s.p)))].sort().forEach(p=>{
  const o=document.createElement("option");o.value=o.textContent=p;srcSel.appendChild(o);
});

function pillbar(id,items,key){
  const el=document.getElementById(id);
  el.innerHTML=items.map(i=>`<div class="pill ${id==='cats'?'cat':''} ${state[key]===i?'active':''}" data-v="${i}">${i}</div>`).join("");
  el.querySelectorAll(".pill").forEach(p=>p.onclick=()=>{state[key]=p.dataset.v;render();});
}
function viewTabs(){
  const tabs=[["events","🎫 Events"],["football","⚽ Football"]];
  document.getElementById("viewTabs").innerHTML=tabs.map(([v,label])=>
    `<div class="pill tab ${state.view===v?'active':''}" data-v="${v}">${label}</div>`).join("");
  document.querySelectorAll("#viewTabs .pill").forEach((p,i)=>p.onclick=()=>{state.view=tabs[i][0];render();});
}
function render(){
  viewTabs();
  const isFoot=state.view==="football";
  document.getElementById("cities").style.display=isFoot?"none":"flex";
  document.getElementById("cats").style.display=isFoot?"none":"flex";
  document.getElementById("floc").style.display=isFoot?"flex":"none";

  let list;
  if(isFoot){
    pillbar("floc",FOOT_LOCS,"floc");
    list=EVENTS.filter(e=>
      e.cat==="Football"&&
      (state.floc==="All"||footballLoc(e)===state.floc)&&
      (!state.src||e.srcs.some(s=>s.p===state.src))&&
      (!state.dupOnly||e.cmp)&&
      (!state.q||(e.n+e.v+e.city).toLowerCase().includes(state.q))
    );
  } else {
    pillbar("cities",CITIES,"city");pillbar("cats",CATS,"cat");
    list=EVENTS.filter(e=>
      e.cat!=="Football"&&
      (state.city==="All"||e.city===state.city||e.city==="All cities")&&
      (state.cat==="All"||e.cat===state.cat)&&
      (!state.src||e.srcs.some(s=>s.p===state.src))&&
      (!state.dupOnly||e.cmp)&&
      (!state.q||(e.n+e.v+e.city+e.cat).toLowerCase().includes(state.q))
    );
  }
  if(state.sort==="date")list.sort((a,b)=>a.date.localeCompare(b.date));
  if(state.sort==="priceAsc")list.sort((a,b)=>(a.pmin??1e9)-(b.pmin??1e9));
  if(state.sort==="priceDesc")list.sort((a,b)=>(b.pmin??-1)-(a.pmin??-1));
  const universe=EVENTS.filter(e=>isFoot?e.cat==="Football":e.cat!=="Football");
  const dupCount=universe.filter(e=>e.cmp).length;
  const srcCount=new Set(universe.flatMap(e=>e.srcs.map(s=>s.p))).size;
  const noun=isFoot?"fixtures":"listings";
  document.getElementById("stats").innerHTML=`Showing <b>${list.length}</b> of <b>${universe.length}</b> ${noun} · <b>${dupCount}</b> cross-platform price comparisons · ${srcCount} source platforms`;
  document.getElementById("grid").innerHTML=list.length?list.map(e=>`
    <div class="card">
      <div class="row">
        <div class="title">${e.n}</div>
        <span class="badge ${catClass[e.cat]||'b-other'}">${e.cat}</span>
      </div>
      ${e.cmp?`<span class="dupbanner">⇄ PRICE COMPARE</span>`:""}
      <div class="meta"><span class="d">${e.dtxt}</span><br>📍 ${e.v} · ${e.city}</div>
      <div class="${e.pmin!=null?'price':'price na'}">${e.ptxt}</div>
      ${e.cmp?`<div class="compare"><div class="t">${e.cmpt||'Platform comparison'}</div>${e.cmp}</div>`:""}
      <div class="srcs">${e.srcs.map(s=>`<a class="src ${srcClass[s.p]||''}" href="${s.u}" target="_blank">${s.p}${s.pmin!=null?` · ${s.cur||'₹'}${s.pmin}`:''} ↗</a>`).join("")}</div>
    </div>`).join(""):`<div class="empty">No events match these filters — try widening them.</div>`;
}
document.getElementById("q").oninput=e=>{state.q=e.target.value.toLowerCase();render();};
document.getElementById("src").onchange=e=>{state.src=e.target.value;render();};
document.getElementById("sort").onchange=e=>{state.sort=e.target.value;render();};
document.getElementById("dupOnly").onchange=e=>{state.dupOnly=e.target.checked;render();};
render();
</script>
__LIVE_SCRIPT__
</body>
</html>
"""

# Polling script for the local dev server (serve.py): checks /api/status every
# few seconds and reloads the page when a newer scrape has landed. Harmless
# no-op on static hosting (Netlify etc.) since that endpoint doesn't exist
# there — the fetch just fails silently and nothing reloads.
LIVE_SCRIPT = """<script>
(function(){
  var known=__VERSION__;
  function poll(){
    fetch('/api/status',{cache:'no-store'}).then(r=>r.json()).then(function(d){
      var dot=document.getElementById('livedot');
      if(dot) dot.textContent=d.scraping?' · 🔄 refreshing…':' · ✓ live';
      if(d.version&&d.version!==known) location.reload();
    }).catch(function(){});
  }
  var sub=document.querySelector('.sub');
  if(sub) sub.innerHTML+='<span id="livedot"></span>';
  poll();
  setInterval(poll,4000);
})();
</script>"""


def generate(events: list[dict], out_path: str, *, live: bool = False, version: float | None = None) -> None:
    cards = _build_cards(events)
    sources = sorted({s["p"] for c in cards for s in c["srcs"]})
    live_script = LIVE_SCRIPT.replace("__VERSION__", json.dumps(version if version is not None else 0)) if live else ""
    html = (
        TEMPLATE
        .replace("__DATA__", json.dumps(cards, ensure_ascii=False))
        .replace("__COUNT__", str(len(cards)))
        .replace("__GENERATED__", datetime.now(timezone.utc).strftime("%a %d %b %Y, %H:%M UTC"))
        .replace("__SOURCES__", " · ".join(sources))
        .replace("__LIVE_SCRIPT__", live_script)
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
