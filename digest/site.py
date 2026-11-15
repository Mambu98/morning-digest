"""Generazione del sito statico (cartella site/) a partire da data/digests/*.json."""

from __future__ import annotations

import json
from datetime import date
from html import escape
from pathlib import Path

MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
          "agosto", "settembre", "ottobre", "novembre", "dicembre"]
WEEKDAYS = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]

CSS = """
:root{--bg:#f7f6f2;--card:#fff;--text:#1d1d1b;--muted:#6b6a65;--line:#e4e2da;--accent:#0f5c4d;--accent-bg:#e3f1ec;--down:#9b2c2c;--down-bg:#f8e5e5}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--card:#1e1e1c;--text:#ecebe6;--muted:#9c9a92;--line:#33322e;--accent:#6fd0b4;--accent-bg:#17352e;--down:#f09595;--down-bg:#3a1d1d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif}
main{max-width:760px;margin:0 auto;padding:32px 18px 64px}
header .date{color:var(--muted);font-size:14px}header .date::first-letter{text-transform:uppercase}
h1{font:500 30px/1.25 Georgia,"Times New Roman",serif;margin:6px 0 28px}
h2{font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:600;margin:36px 0 12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 20px 14px;margin-bottom:14px}
.meta{display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:13px;color:var(--muted);margin-bottom:6px}
.pill{background:var(--accent-bg);color:var(--accent);border-radius:999px;padding:1px 10px;font-weight:600}
.pill.explore{background:transparent;border:1px solid var(--line);color:var(--muted);font-weight:500}
.card h3{font:500 20px/1.35 Georgia,serif;margin:4px 0 10px}
a{color:inherit;text-decoration-color:var(--line);text-underline-offset:3px}a:hover{text-decoration-color:var(--accent)}
.why{border-left:3px solid var(--accent);padding-left:12px;margin:10px 0}
.why b{color:var(--accent);font-weight:600}
.note{font-size:12px;color:var(--muted)}
.row{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:8px}
.votes{display:flex;gap:6px;flex-shrink:0}
.votes button{width:36px;height:32px;border-radius:8px;border:1px solid var(--line);background:transparent;color:var(--muted);font-size:18px;cursor:pointer;line-height:1}
.votes button.on.up{background:var(--accent-bg);color:var(--accent);border-color:var(--accent)}
.votes button.on.down{background:var(--down-bg);color:var(--down);border-color:var(--down)}
.votes button.err{border-color:var(--down)}
.brief{display:flex;justify-content:space-between;gap:12px;padding:14px 0;border-bottom:1px solid var(--line)}
.brief p{margin:2px 0 0;color:var(--muted);font-size:14px}
.brief .t{font-weight:500}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:600}
.scroll{overflow-x:auto}
footer{margin-top:40px;font-size:13px;color:var(--muted)}
ul.archive{list-style:none;padding:0}ul.archive li{padding:10px 0;border-bottom:1px solid var(--line)}
"""

JS = """
(function(){
  var KEY='md-votes';
  function load(){try{return JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){return {}}}
  function save(s){try{localStorage.setItem(KEY,JSON.stringify(s))}catch(e){}}
  function paint(box,v){box.querySelector('.up').classList.toggle('on',v===1);box.querySelector('.down').classList.toggle('on',v===-1)}
  var state=load();
  document.querySelectorAll('.votes').forEach(function(box){
    var item=JSON.parse(box.dataset.item);
    paint(box,state[item.date+':'+item.id]||0);
    box.querySelectorAll('button').forEach(function(btn){
      btn.addEventListener('click',function(){
        var key=item.date+':'+item.id, cur=state[key]||0, v=parseInt(btn.dataset.v,10), nv=cur===v?0:v;
        var payload=Object.assign({},item,{vote:nv});
        fetch('/api/vote',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)})
          .then(function(r){if(!r.ok)throw new Error(r.status);state[key]=nv;save(state);paint(box,nv)})
          .catch(function(){btn.classList.add('err');setTimeout(function(){btn.classList.remove('err')},1500)});
      });
    });
  });
})();
"""


def _it_date(d: str) -> str:
    dt = date.fromisoformat(d)
    return f"{WEEKDAYS[dt.weekday()]} {dt.day} {MONTHS[dt.month - 1]} {dt.year}"


def _votes(item: dict, day: str, kind: str) -> str:
    payload = {"id": item["id"], "date": day, "kind": kind, "title": item["title"],
               "source": item["source"], "category": item.get("category", ""), "tags": item.get("tags", [])}
    data = escape(json.dumps(payload, ensure_ascii=False), quote=True)
    return (f'<div class="votes" data-item="{data}">'
            f'<button class="up" data-v="1" aria-label="Mi interessa">+</button>'
            f'<button class="down" data-v="-1" aria-label="Non mi interessa">−</button></div>')


def _page(title: str, body: str, root: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>{escape(title)}</title><style>{CSS}</style></head>
<body><main>{body}
<footer><a href="{root}index.html">Oggi</a> · <a href="{root}archive/index.html">Archivio</a></footer>
</main><script>{JS}</script></body></html>
"""


def render_digest(d: dict, root: str) -> str:
    day = d["date"]
    parts = [f'<header><div class="date">{_it_date(day)}</div><h1>{escape(d.get("headline") or "Morning digest")}</h1></header>',
             "<h2>Le tre notizie</h2>"]
    for it in d["top"]:
        link = it.get("original_url") or it["url"]
        explore = '<span class="pill explore">esplorativa</span>' if it.get("exploratory") else ""
        note = "" if it.get("verified") else '<div class="note">Sintesi basata sul solo titolo: fonte non letta.</div>'
        parts.append(f"""<article class="card"><div class="meta"><span class="pill">{escape(it.get('category', ''))}</span>{explore}<span>{escape(it['source'])}</span></div>
<h3><a href="{escape(link, quote=True)}" target="_blank" rel="noopener">{escape(it['title'])}</a></h3>
<p>{escape(it.get('summary', ''))}</p><div class="why"><b>Perché conta.</b> {escape(it.get('why_it_matters', ''))}</div>
<div class="row">{note or '<span></span>'}{_votes(it, day, 'top')}</div></article>""")

    if d.get("briefs"):
        parts.append("<h2>In breve</h2>")
        for it in d["briefs"]:
            parts.append(f"""<div class="brief"><div><a class="t" href="{escape(it['url'], quote=True)}" target="_blank" rel="noopener">{escape(it['title'])}</a>
<p>{escape(it.get('one_liner', ''))} · {escape(it['source'])}</p></div>{_votes(it, day, 'brief')}</div>""")

    if d.get("deals"):
        parts.append('<h2>Deal tracker di oggi</h2><div class="scroll"><table><tr><th>Target</th><th>Tipo</th><th>Acquirente / sponsor</th><th>EV (€m)</th><th>Fonte</th></tr>')
        for dl in d["deals"]:
            ev = "" if dl.get("ev_eur_m") is None else f"{dl['ev_eur_m']:,.0f}".replace(",", ".")
            parts.append(f"<tr><td>{escape(dl.get('target') or '')}</td><td>{escape(dl.get('deal_type') or '')}</td>"
                         f"<td>{escape(dl.get('buyer') or '')}</td><td>{ev}</td>"
                         f"<td><a href=\"{escape(dl['url'], quote=True)}\" target=\"_blank\" rel=\"noopener\">{escape(dl.get('source') or 'link')}</a></td></tr>")
        parts.append("</table></div>")
    return _page(f"Digest {day}", "\n".join(parts), root)


def build_all(digests_dir: Path, site_dir: Path) -> None:
    (site_dir / "archive").mkdir(parents=True, exist_ok=True)
    files = sorted(digests_dir.glob("*.json"), reverse=True) if digests_dir.exists() else []
    digests = [json.loads(f.read_text(encoding="utf-8")) for f in files]

    for d in digests:
        (site_dir / "archive" / f"{d['date']}.html").write_text(render_digest(d, "../"), encoding="utf-8")

    if digests:
        (site_dir / "index.html").write_text(render_digest(digests[0], ""), encoding="utf-8")
    else:
        body = ('<header><div class="date">In attesa</div><h1>Il primo digest arriva domattina.</h1></header>'
                "<p>Puoi anche lanciarlo subito da GitHub: Actions → Morning digest → Run workflow.</p>")
        (site_dir / "index.html").write_text(_page("Morning digest", body, ""), encoding="utf-8")

    items = "".join(f'<li><a href="{d["date"]}.html">{_it_date(d["date"]).capitalize()}</a>'
                    f'<div class="note">{escape(d.get("headline", ""))}</div></li>' for d in digests)
    body = f'<header><h1>Archivio</h1></header><ul class="archive">{items or "<li>Ancora vuoto.</li>"}</ul>'
    (site_dir / "archive" / "index.html").write_text(_page("Archivio digest", body, "../"), encoding="utf-8")
