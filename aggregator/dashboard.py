"""Generates dashboard.html from a list of event dicts.

Design ported from the original "India Events Dashboard" snapshot: dark
theme, city/category pill filters, per-category badges, colored source
chips, and a price-comparison box on cards found on 2+ platforms.

Events sharing a group_id (see aggregator.dedupe) are merged into ONE
card listing every platform, with an auto-generated comparison line.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

# Normalize scraper categories to display labels
CATEGORY_LABELS = {
    "Kids": "Kids & Family",
    "Nightlife": "Beer & Nightlife",
    "Music": "Music & Culture",
    "Markets": "Markets & Expos",
}

# Extra booking chips for movies: these platforms block scraping but are
# where people actually book, so cards link straight to them.
MOVIE_BOOKING_LINKS = [
    {"p": "BookMyShow", "u": "https://in.bookmyshow.com/explore/movies"},
    {"p": "District", "u": "https://www.district.in/movies/"},
]


def _fmt_price(lo, hi) -> str:
    f = lambda n: f"₹{int(n):,}" if n == int(n) else f"₹{n:,}"
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
    priced = [s for s in srcs if s.get("pmin") is not None]
    if len(srcs) < 2:
        return None
    if len(priced) >= 2:
        best = min(priced, key=lambda s: s["pmin"])
        parts = []
        for s in sorted(priced, key=lambda s: s["pmin"]):
            cls = "win" if s["pmin"] == best["pmin"] else "lose"
            parts.append(f"{s['p']}: <span class='{cls}'>₹{int(s['pmin'])}</span>")
        line = " · ".join(parts)
        prices = sorted({s["pmin"] for s in priced})
        if len(prices) > 1:
            diff = int(prices[-1] - prices[0])
            line += f" — {best['p']} is ~₹{diff} cheaper for the same show."
        else:
            line += " — same price, book on either."
        return line
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
        city = "All cities" if lead["city"] in ("All India", "All cities") else lead["city"]

        srcs, seen_src = [], set()
        for m in members:
            if m["source"] not in seen_src:
                srcs.append({"p": m["source"], "u": m["url"], "pmin": m["price_min"]})
                seen_src.add(m["source"])
        if category == "Movies":
            for link in MOVIE_BOOKING_LINKS:
                if link["p"] not in seen_src:
                    srcs.append({**link, "pmin": None})

        prices = [m["price_min"] for m in members if m["price_min"] is not None]
        highs = [m["price_max"] for m in members if m["price_max"] is not None]
        date = min((m["date"] for m in members if m["date"]), default="")
        venue = next((m["venue"] for m in members if m["venue"]), "")

        cmp_line = _comparison(srcs) if len(seen_src) > 1 else None
        if category == "Movies" and not cmp_line:
            cmp_line = None  # movie chips are booking links, not scraped prices

        cards.append({
            "n": lead["title"],
            "city": city,
            "cat": category,
            "date": (date or "9999")[:10],
            "dtxt": _fmt_date(date),
            "v": venue or ("Cinemas nationwide" if category == "Movies" else city),
            "pmin": min(prices) if prices else None,
            "ptxt": _fmt_price(min(prices) if prices else None, max(highs) if highs else None),
            "srcs": srcs,
            "cmp": cmp_line,
        })
    cards.sort(key=lambda c: c["date"])
    return cards


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>India Events Dashboard — All Listings, One Place</title>
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
  .compare{background:var(--card2);border:1px dashed #4c357c;border-radius:10px;padding:10px 12px;font-size:12.5px;line-height:1.6}
  .compare .t{color:var(--purple);font-weight:700;font-size:11px;letter-spacing:.5px;text-transform:uppercase;margin-bottom:3px}
  .compare .win{color:var(--green);font-weight:700}
  .compare .lose{color:var(--red)}
  .dupbanner{display:inline-block;font-size:10.5px;background:#2b1d47;color:var(--purple);border-radius:6px;padding:3px 8px;font-weight:700;letter-spacing:.3px}
  .note{margin-top:28px;background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px 18px;color:var(--muted);font-size:12.5px;line-height:1.7}
  .note b{color:var(--text)}
  .empty{grid-column:1/-1;text-align:center;color:var(--muted);padding:60px 0;font-size:15px}
</style>
</head>
<body>
<div class="wrap">
  <h1>🎟️ India Events <span>Dashboard</span></h1>
  <div class="sub">Snapshot: __GENERATED__ · Sources: __SOURCES__ · __COUNT__ listings</div>

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
  <div class="stats" id="stats"></div>
  <div class="grid" id="grid"></div>

  <div class="note">
    <b>How to read this:</b> Each card shows the event with every platform it was found on — click a source chip to open that listing and book. Cards with a
    <span class="dupbanner">⇄ PRICE COMPARE</span> banner were found on 2+ platforms — the comparison box shows which is cheaper.<br><br>
    <b>Caveats:</b> Prices, dates and availability change fast — always confirm on the booking page. BookMyShow &amp; District block full automated scraping, so their chips are booking links rather than scraped prices; AllEvents and Eventz are indexed directly, movies come from release calendars. Movie ticket prices vary by cinema/format (typically ₹150–600). Re-run <b>python run.py</b> anytime for a fresh snapshot.
  </div>
</div>

<script>
const EVENTS=__DATA__;

const CITIES=["All",...new Set(EVENTS.map(e=>e.city).filter(c=>c!=="All cities"))].concat(EVENTS.some(e=>e.city==="All cities")?[]:[]);
const CATS=["All",...new Set(EVENTS.map(e=>e.cat))];
const catClass={"Comedy":"b-comedy","Movies":"b-movies","Kids & Family":"b-kids","Beer & Nightlife":"b-beer","Magic":"b-magic","Music & Culture":"b-music","Markets & Expos":"b-market"};
const srcClass={"AllEvents":"s-allevents","District":"s-district","Eventz":"s-eventz","BookMyShow":"s-bms","CherishX":"s-cherishx","Wikipedia":"s-wiki"};
let state={city:"All",cat:"All",q:"",src:"",sort:"date",dupOnly:false};

const srcSel=document.getElementById("src");
[...new Set(EVENTS.flatMap(e=>e.srcs.map(s=>s.p)))].sort().forEach(p=>{
  const o=document.createElement("option");o.value=o.textContent=p;srcSel.appendChild(o);
});

function pillbar(id,items,key){
  const el=document.getElementById(id);
  el.innerHTML=items.map(i=>`<div class="pill ${id==='cats'?'cat':''} ${state[key]===i?'active':''}" data-v="${i}">${i}</div>`).join("");
  el.querySelectorAll(".pill").forEach(p=>p.onclick=()=>{state[key]=p.dataset.v;render();});
}
function render(){
  pillbar("cities",CITIES,"city");pillbar("cats",CATS,"cat");
  let list=EVENTS.filter(e=>
    (state.city==="All"||e.city===state.city||e.city==="All cities")&&
    (state.cat==="All"||e.cat===state.cat)&&
    (!state.src||e.srcs.some(s=>s.p===state.src))&&
    (!state.dupOnly||e.cmp)&&
    (!state.q||(e.n+e.v+e.city+e.cat).toLowerCase().includes(state.q))
  );
  if(state.sort==="date")list.sort((a,b)=>a.date.localeCompare(b.date));
  if(state.sort==="priceAsc")list.sort((a,b)=>(a.pmin??1e9)-(b.pmin??1e9));
  if(state.sort==="priceDesc")list.sort((a,b)=>(b.pmin??-1)-(a.pmin??-1));
  const dupCount=EVENTS.filter(e=>e.cmp).length;
  const srcCount=new Set(EVENTS.flatMap(e=>e.srcs.map(s=>s.p))).size;
  document.getElementById("stats").innerHTML=`Showing <b>${list.length}</b> of <b>${EVENTS.length}</b> listings · <b>${dupCount}</b> cross-platform price comparisons · ${srcCount} source platforms`;
  document.getElementById("grid").innerHTML=list.length?list.map(e=>`
    <div class="card">
      <div class="row">
        <div class="title">${e.n}</div>
        <span class="badge ${catClass[e.cat]||'b-other'}">${e.cat}</span>
      </div>
      ${e.cmp?`<span class="dupbanner">⇄ PRICE COMPARE</span>`:""}
      <div class="meta"><span class="d">${e.dtxt}</span><br>📍 ${e.v} · ${e.city}</div>
      <div class="${e.pmin!=null?'price':'price na'}">${e.ptxt}</div>
      ${e.cmp?`<div class="compare"><div class="t">Platform comparison</div>${e.cmp}</div>`:""}
      <div class="srcs">${e.srcs.map(s=>`<a class="src ${srcClass[s.p]||''}" href="${s.u}" target="_blank">${s.p} ↗</a>`).join("")}</div>
    </div>`).join(""):`<div class="empty">No events match these filters — try widening them.</div>`;
}
document.getElementById("q").oninput=e=>{state.q=e.target.value.toLowerCase();render();};
document.getElementById("src").onchange=e=>{state.src=e.target.value;render();};
document.getElementById("sort").onchange=e=>{state.sort=e.target.value;render();};
document.getElementById("dupOnly").onchange=e=>{state.dupOnly=e.target.checked;render();};
render();
</script>
</body>
</html>
"""


def generate(events: list[dict], out_path: str) -> None:
    cards = _build_cards(events)
    sources = sorted({s["p"] for c in cards for s in c["srcs"]})
    html = (
        TEMPLATE
        .replace("__DATA__", json.dumps(cards, ensure_ascii=False))
        .replace("__COUNT__", str(len(cards)))
        .replace("__GENERATED__", datetime.now(timezone.utc).strftime("%a %d %b %Y, %H:%M UTC"))
        .replace("__SOURCES__", " · ".join(sources))
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
