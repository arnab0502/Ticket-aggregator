"""Generates dashboard.html from a list of event dicts.

The dashboard is a single self-contained HTML file: the event data is
embedded as JSON and all filtering/search/sorting happens client-side,
so it can be opened directly or hosted on GitHub Pages.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>India Events Aggregator</title>
<style>
  :root { --bg:#0f1220; --card:#1a1f35; --text:#e8eaf6; --muted:#9aa0c3; --accent:#7c5cff; --good:#3ddc84; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--text); font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif; padding:24px; }
  h1 { font-size:1.6rem; margin-bottom:4px; }
  .sub { color:var(--muted); margin-bottom:20px; font-size:.9rem; }
  .controls { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:20px; align-items:center; }
  select, input[type=search] { background:var(--card); color:var(--text); border:1px solid #2c3252; border-radius:8px; padding:8px 12px; font-size:.9rem; }
  input[type=search] { min-width:220px; }
  label.toggle { display:flex; gap:6px; align-items:center; color:var(--muted); font-size:.9rem; cursor:pointer; }
  .count { color:var(--muted); font-size:.85rem; margin-left:auto; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:16px; }
  .card { background:var(--card); border:1px solid #262c4a; border-radius:12px; padding:16px; display:flex; flex-direction:column; gap:8px; }
  .card.multi { border-color:var(--accent); }
  .tagrow { display:flex; gap:6px; flex-wrap:wrap; }
  .tag { font-size:.7rem; padding:2px 8px; border-radius:999px; background:#262c4a; color:var(--muted); }
  .tag.src { background:#2b2350; color:#c4b5fd; }
  .tag.dup { background:#173a2a; color:var(--good); }
  .title { font-weight:600; line-height:1.3; }
  .meta { color:var(--muted); font-size:.82rem; }
  .price { font-weight:600; color:var(--good); }
  .compare { background:#141830; border-radius:8px; padding:8px 10px; font-size:.8rem; }
  .compare div { display:flex; justify-content:space-between; padding:2px 0; color:var(--muted); }
  .compare .best { color:var(--good); }
  a.book { margin-top:auto; text-align:center; background:var(--accent); color:#fff; text-decoration:none; padding:8px; border-radius:8px; font-size:.9rem; }
  a.book:hover { filter:brightness(1.15); }
  .empty { color:var(--muted); padding:40px; text-align:center; grid-column:1/-1; }
</style>
</head>
<body>
<h1>🎟️ India Events Aggregator</h1>
<div class="sub">__COUNT__ listings · scraped __GENERATED__ · sources: __SOURCES__</div>

<div class="controls">
  <input type="search" id="q" placeholder="Search events…">
  <select id="city"><option value="">All cities</option></select>
  <select id="category"><option value="">All categories</option></select>
  <select id="source"><option value="">All sources</option></select>
  <select id="sort">
    <option value="date">Sort: Date</option>
    <option value="price">Sort: Price (low → high)</option>
    <option value="title">Sort: Title</option>
  </select>
  <label class="toggle"><input type="checkbox" id="multi"> Price-compare only</label>
  <span class="count" id="count"></span>
</div>

<div class="grid" id="grid"></div>

<script>
const EVENTS = __DATA__;

const $ = id => document.getElementById(id);

function fill(sel, values) {
  [...new Set(values)].sort().forEach(v => {
    const o = document.createElement('option'); o.value = o.textContent = v; sel.appendChild(o);
  });
}
fill($('city'), EVENTS.map(e => e.city));
fill($('category'), EVENTS.map(e => e.category));
fill($('source'), EVENTS.map(e => e.source));

function fmtPrice(e) {
  if (e.price_min == null) return '';
  const f = n => '₹' + Number(n).toLocaleString('en-IN');
  return e.price_min === e.price_max || e.price_max == null ? f(e.price_min) : f(e.price_min) + ' – ' + f(e.price_max);
}

function fmtDate(d) {
  if (!d) return '';
  const t = new Date(d);
  return isNaN(t) ? d : t.toLocaleString('en-IN', {day:'numeric', month:'short', hour:'numeric', minute:'2-digit'});
}

function groupPrices(ev) {
  const peers = EVENTS.filter(e => e.group_id === ev.group_id && e.price_min != null);
  if (peers.length < 2) return null;
  const best = Math.min(...peers.map(e => e.price_min));
  return peers.map(e =>
    `<div class="${e.price_min === best ? 'best' : ''}"><span>${e.source}</span><span>₹${e.price_min}</span></div>`
  ).join('');
}

function render() {
  const q = $('q').value.toLowerCase(), city = $('city').value, cat = $('category').value,
        src = $('source').value, multi = $('multi').checked, sort = $('sort').value;

  let list = EVENTS.filter(e =>
    (!q || (e.title + ' ' + e.venue).toLowerCase().includes(q)) &&
    (!city || e.city === city) && (!cat || e.category === cat) &&
    (!src || e.source === src) && (!multi || e.multi_source));

  list.sort((a, b) => {
    if (sort === 'price') return (a.price_min ?? 1e9) - (b.price_min ?? 1e9);
    if (sort === 'title') return a.title.localeCompare(b.title);
    return (a.date || '9999').localeCompare(b.date || '9999');
  });

  $('count').textContent = list.length + ' shown';
  $('grid').innerHTML = list.length ? list.map(e => {
    const cmp = e.multi_source ? groupPrices(e) : null;
    return `<div class="card ${e.multi_source ? 'multi' : ''}">
      <div class="tagrow">
        <span class="tag">${e.city}</span><span class="tag">${e.category}</span>
        <span class="tag src">${e.source}</span>
        ${e.multi_source ? '<span class="tag dup">on multiple sites</span>' : ''}
      </div>
      <div class="title">${e.title}</div>
      <div class="meta">${fmtDate(e.date)}${e.venue ? ' · ' + e.venue : ''}</div>
      <div class="price">${fmtPrice(e)}</div>
      ${cmp ? '<div class="compare">' + cmp + '</div>' : ''}
      <a class="book" href="${e.url}" target="_blank" rel="noopener">View / Book →</a>
    </div>`;
  }).join('') : '<div class="empty">No events match your filters.</div>';
}

['q','city','category','source','sort','multi'].forEach(id => {
  $(id).addEventListener(id === 'q' ? 'input' : 'change', render);
});
render();
</script>
</body>
</html>
"""


def generate(events: list[dict], out_path: str) -> None:
    sources = sorted({e["source"] for e in events}) or ["none"]
    html = (
        TEMPLATE
        .replace("__DATA__", json.dumps(events, ensure_ascii=False))
        .replace("__COUNT__", str(len(events)))
        .replace("__GENERATED__", datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"))
        .replace("__SOURCES__", ", ".join(sources))
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
