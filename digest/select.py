"""Selezione e sintesi con Claude Code (headless, piano Pro via CLAUDE_CODE_OAUTH_TOKEN).

Due chiamate brevi invece di un agente che naviga:
  1. SELEZIONE: Claude sceglie dai titoli (nessuno strumento).
  2. SCRITTURA: Python legge gli articoli scelti (articles.py) e Claude scrive le sintesi dal testo.
     Solo per gli articoli che Python non riesce a leggere (paywall) Claude può cercare con WebSearch/WebFetch.
"""

from __future__ import annotations

import json
import os
import subprocess

from . import articles

CATEGORIES = ["LBO / PE Italia", "LevFin & Private credit", "Fondi PE", "M&A Italia", "Piazza Affari / EGM", "Macro & Mercati"]
DEAL_TYPES = ["LBO", "Secondary buyout", "Add-on", "M&A", "Minoranza", "Exit", "Financing", "Refinancing", "Fundraising", "IPO", "OPA / Delisting"]
MODEL = os.environ.get("DIGEST_MODEL", "sonnet")
TOP_N = 3
RANKED_N = 5

DEAL_SCHEMA = ('{"id": "id candidato", "target": "string", "buyer": "string o null", "seller": "string o null", '
               '"deal_type": "string", "sector": "string o null", "country": "string o null", "ev_eur_m": "numero o null", '
               '"ev_ebitda": "numero o null", "leverage_x": "numero o null", "debt_package": "string o null", '
               '"banks_advisors": "string o null"}')

PROMPT_SELECT = """Sei il redattore del digest mattutino personale di un banker. Data di oggi: {date}.

## Profilo del lettore
{profile}

## Feedback del lettore (voti +/− sul sito)
{feedback}

## Fonti autorevoli da privilegiare
{preferred}
A parità di notizia scegli la fonte autorevole; scarta aggregatori, siti di bassa qualità e notizie fuori profilo (es. sport).

## Notizie candidate (ultime 36 ore)
Formato: [id] data | fonte | topic di ricerca | titolo
{candidates}

## Compito (lavora solo sui titoli, non usare strumenti)
1. "top_ranked": le {ranked_n} notizie più rilevanti in ordine di importanza (le prime {top_n} andranno in apertura,
   le altre sono riserve). Segui le priorità del profilo e pesa il feedback. Una delle prime {top_n} può essere
   "esplorativa" (fuori dalle preferenze recenti ma importante): "exploratory": true.
2. "briefs": altre 6-8 notizie, con "one_liner" in italiano di massimo 25 parole basato sul titolo.
3. "international": 3-4 pillole dal mondo (notizie NON italiane), preferibilmente da Financial Times, Bloomberg,
   Reuters, WSJ: deal e trend globali di PE / LevFin / private credit e macro. "one_liner" in italiano, massimo 30 parole,
   basato sul titolo. Non ripetere notizie già in top_ranked o briefs.
4. Evita doppioni: se la stessa notizia compare da più fonti, scegline una sola.
5. "deals": TUTTE le operazioni presenti tra i candidati (M&A, LBO, financing, fundraising, IPO, OPA).
   Campi compilati solo con informazioni esplicite nel titolo, altrimenti null. Mai stimare.
6. "headline": una frase in italiano che sintetizza il tema della giornata.

Categorie ammesse: {categories}
Tipi di deal ammessi: {deal_types}

Rispondi SOLO con un oggetto JSON valido:
{{
  "headline": "string",
  "top_ranked": [{{"id": "id candidato", "category": "string", "tags": ["string"], "exploratory": false}}],
  "briefs": [{{"id": "id candidato", "category": "string", "one_liner": "string", "tags": ["string"]}}],
  "international": [{{"id": "id candidato", "category": "string", "one_liner": "string", "tags": ["string"]}}],
  "deals": [{deal_schema}]
}}
"""

PROMPT_WRITE = """Scrivi le sintesi delle notizie di apertura del digest mattutino di un banker
(LevFin / structured lending a Milano, interessato a PE, private credit, M&A Italia, macro).

Per ogni notizia trovi titolo, fonte e il TESTO dell'articolo letto in automatico.
- "summary": 2-3 frasi in italiano con i fatti chiave.
- "why_it_matters": 1-2 frasi dal punto di vista di un banker LevFin (sponsor, multipli, leva, chi finanzia, cosa dice sul mercato).
- Numeri (EV, multipli, leva, importi) SOLO se presenti nel testo. Mai stimare o dedurre.
- "verified": true se hai basato la sintesi su un testo dell'articolo.
Se il testo è "NON DISPONIBILE", puoi usare WebSearch e WebFetch (massimo 3 chiamate per notizia) per trovare
l'articolo o una fonte autorevole equivalente; se ci riesci "verified": true e "original_url" = URL letto,
altrimenti "verified": false e limita la sintesi ai fatti del titolo. Per le notizie con testo NON usare strumenti.

Se nel testo ci sono operazioni (M&A, LBO, financing, fundraising), compila anche "deals" con i dati espliciti
(null se assenti, mai stimare).

{items}

Rispondi SOLO con un oggetto JSON valido:
{{
  "top": [{{"id": "id", "summary": "string", "why_it_matters": "string", "verified": true, "original_url": "string o null"}}],
  "deals": [{deal_schema}]
}}
"""


def _candidate_lines(candidates: list[dict]) -> str:
    return "\n".join(
        f"[{c['id']}] {(c['published'] or '')[:10]} | {c['source']} | {c['topic']} | {c['title']}" for c in candidates
    )


def build_select_prompt(candidates: list[dict], profile: str, feedback: str, date: str, preferred=()) -> str:
    return PROMPT_SELECT.format(
        date=date, profile=profile.strip(), feedback=feedback,
        preferred=", ".join(preferred) or "nessuna indicazione",
        candidates=_candidate_lines(candidates), ranked_n=RANKED_N, top_n=TOP_N,
        categories=", ".join(CATEGORIES), deal_types=", ".join(DEAL_TYPES), deal_schema=DEAL_SCHEMA,
    )


def build_write_prompt(picks: list[dict]) -> str:
    blocks = []
    for p in picks:
        body = p["text"] or "NON DISPONIBILE"
        url = p["resolved_url"] or p["url"]
        blocks.append(f"### [{p['id']}] {p['title']}\nFonte: {p['source']}\nURL: {url}\nTesto:\n{body}\n")
    return PROMPT_WRITE.format(items="\n".join(blocks), deal_schema=DEAL_SCHEMA)


def _extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"Nessun JSON nella risposta di Claude:\n{text[:2000]}")
    return json.loads(text[start : end + 1])


def ask_claude(prompt: str, label: str, tools: bool = False, max_turns: int = 2) -> dict:
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--model", MODEL, "--max-turns", str(max_turns)]
    if tools:
        cmd += ["--allowedTools", "WebSearch", "WebFetch"]  # deve restare l'ultima opzione (accetta più valori)
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    if res.returncode != 0:
        raise RuntimeError(f"Claude Code ({label}) errore {res.returncode}:\n{res.stderr[-3000:]}\n{res.stdout[-3000:]}")
    envelope = json.loads(res.stdout)
    usage = envelope.get("usage") or {}
    tokens_in = sum(usage.get(k) or 0 for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    print(f"  Claude [{label}]: {envelope.get('num_turns')} turni, {round((envelope.get('duration_ms') or 0) / 1000)}s, "
          f"token in {tokens_in:,} / out {usage.get('output_tokens') or 0:,}")
    for d in (envelope.get("permission_denials") or [])[:5]:
        print(f"    negato: {d.get('tool_name')}")
    if envelope.get("is_error"):
        raise RuntimeError(f"Claude Code ({label}): {envelope.get('result') or envelope}")
    return _extract_json(envelope.get("result", ""))


def run(candidates: list[dict], profile: str, feedback: str, date: str, preferred=()) -> dict:
    by_id = {c["id"]: c for c in candidates}

    sel = ask_claude(build_select_prompt(candidates, profile, feedback, date, preferred), "selezione")
    ranked = [e for e in sel.get("top_ranked", []) if e.get("id") in by_id][:RANKED_N]
    chosen = ranked[:TOP_N]
    if not chosen:
        raise ValueError("Claude non ha restituito notizie valide per la sezione top.")

    print("  Lettura articoli (Python, zero token)")
    picks = []
    for e in chosen:
        c = by_id[e["id"]]
        art = articles.read(c)
        picks.append({**c, "text": art["text"], "resolved_url": art["url"], "meta": e})

    need_tools = any(p["text"] is None for p in picks)
    written = ask_claude(build_write_prompt(picks), "scrittura", tools=need_tools, max_turns=15 if need_tools else 2)
    texts = {t.get("id"): t for t in written.get("top", [])}

    top = []
    for p in picks:
        t = texts.get(p["id"], {})
        top.append({
            **p["meta"],
            "summary": t.get("summary", ""), "why_it_matters": t.get("why_it_matters", ""),
            "verified": bool(t.get("verified")),
            "original_url": t.get("original_url") or p["resolved_url"],
        })

    deals = {d.get("id"): d for d in sel.get("deals", []) if d.get("id")}
    deals.update({d.get("id"): d for d in written.get("deals", []) if d.get("id")})  # i dati dal testo prevalgono
    return {"headline": sel.get("headline", ""), "top": top, "briefs": sel.get("briefs", []),
            "international": sel.get("international", []), "deals": list(deals.values())}


def mock(candidates: list[dict]) -> dict:
    """Digest finto per provare sito e pipeline senza consumare il piano."""
    return {
        "headline": "Digest di prova (modalità mock): nessuna chiamata a Claude.",
        "top": [
            {"id": c["id"], "category": CATEGORIES[i % len(CATEGORIES)], "summary": "Testo di prova.",
             "why_it_matters": "Testo di prova.", "tags": ["test"], "verified": False,
             "exploratory": i == 2, "original_url": None}
            for i, c in enumerate(candidates[:3])
        ],
        "briefs": [
            {"id": c["id"], "category": CATEGORIES[i % len(CATEGORIES)], "one_liner": c["title"], "tags": []}
            for i, c in enumerate(candidates[3:10])
        ],
        "international": [
            {"id": c["id"], "category": "Macro & Mercati", "one_liner": c["title"], "tags": []}
            for c in candidates[10:14]
        ],
        "deals": [],
    }


def _num(value):
    if value in (None, "", "null"):
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def validate(raw: dict, candidates: list[dict]) -> dict:
    """Tiene solo id esistenti (niente URL inventati) e riporta titolo/fonte/URL dai candidati."""
    by_id = {c["id"]: c for c in candidates}
    used: set[str] = set()

    def base(entry: dict) -> dict | None:
        c = by_id.get(entry.get("id"))
        if not c or c["id"] in used:
            return None
        used.add(c["id"])
        return {"id": c["id"], "title": c["title"], "source": c["source"], "url": c["url"],
                "published": c["published"], "category": entry.get("category") or "", "tags": entry.get("tags") or []}

    top = []
    for e in raw.get("top", [])[:TOP_N]:
        b = base(e)
        if b:
            orig = e.get("original_url")
            b.update(summary=e.get("summary", ""), why_it_matters=e.get("why_it_matters", ""),
                     verified=bool(e.get("verified")), exploratory=bool(e.get("exploratory")),
                     original_url=orig if isinstance(orig, str) and orig.startswith("http") else None)
            top.append(b)

    briefs = []
    for e in raw.get("briefs", [])[:8]:
        b = base(e)
        if b:
            b["one_liner"] = e.get("one_liner", "")
            briefs.append(b)

    international = []
    for e in raw.get("international", [])[:4]:
        b = base(e)
        if b:
            b["one_liner"] = e.get("one_liner", "")
            international.append(b)

    deals = []
    for e in raw.get("deals", []):
        c = by_id.get(e.get("id"))
        if not c or not e.get("target"):
            continue
        deals.append({
            "date": (c["published"] or "")[:10],
            "target": e.get("target"), "buyer": e.get("buyer"), "seller": e.get("seller"),
            "deal_type": e.get("deal_type"), "sector": e.get("sector"), "country": e.get("country"),
            "ev_eur_m": _num(e.get("ev_eur_m")), "ev_ebitda": _num(e.get("ev_ebitda")),
            "leverage_x": _num(e.get("leverage_x")), "debt_package": e.get("debt_package"),
            "banks_advisors": e.get("banks_advisors"), "source": c["source"], "url": c["url"], "title": c["title"],
        })

    if not top:
        raise ValueError("Claude non ha restituito notizie valide per la sezione top.")
    return {"headline": raw.get("headline", ""), "top": top, "briefs": briefs, "international": international, "deals": deals}
