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
   "category" coerente con il contenuto (es. "LBO / PE Italia" solo per operazioni italiane).
2. "briefs": altre 6-8 notizie, con "one_liner" in italiano di massimo 25 parole basato sul titolo.
3. "international": 3-4 pillole dal mondo (notizie NON italiane), preferibilmente da Financial Times, Bloomberg,
   Reuters, WSJ: deal e trend globali di PE / LevFin / private credit e macro. "one_liner" in italiano, massimo 30 parole,
   basato sul titolo. Non ripetere notizie già in top_ranked o briefs.
4. Evita doppioni: se la stessa notizia compare da più fonti, scegline una sola.
5. "deals": le operazioni presenti tra i candidati (M&A, LBO, financing, fundraising, IPO, OPA) con un target
   (o un fondo, per il fundraising) identificato per nome. Escludi trend generici e società non nominate.
   "deal_type" deve essere esattamente uno dei tipi ammessi. Campi solo con informazioni esplicite, altrimenti null.
6. "headline": una frase in italiano che sintetizza il tema della giornata.
7. "market_pill": la pillola mercati del giorno, costruita SOLO sui titoli macro/mercati dei candidati.
   - "what_is_happening": 2-3 frasi su cosa sta muovendo i mercati (banche centrali, tassi, valute, credito, temi).
   - "for_you": 1-2 frasi su cosa significa per il portafoglio del lettore, confrontandolo con la sua tesi di
     allocazione (vedi profilo): la conferma, la mette in discussione o non la tocca?
   - "watch": uno spunto concreto a livello di asset allocation o di cosa monitorare (un dato in uscita, una soglia,
     un tema). Se non c'è niente da fare, dillo ("nessuna azione: ...").
   - "stock_ideas": 0-2 spunti su singoli titoli quotati, SOLO se una notizia tra i candidati offre un catalizzatore
     concreto (OPA, deal, risultati, rating, cambio di guidance). Preferenza per small/mid cap italiane ed EGM e per i
     temi del portafoglio. Per ciascuno: "name", "ticker" (null se non lo conosci con certezza),
     "direction" ("Acquisto", "Vendita" o "Da monitorare"), "rationale" (1-2 frasi: il catalizzatore e perché),
     "risk" (1 frase: cosa smentirebbe lo spunto), "id" (candidato da cui nasce).
     Niente target price né numeri che non siano nei titoli. Se non ci sono catalizzatori veri, lista vuota.
   - "ids": id dei candidati su cui ti basi.
   Nessun numero che non sia nei titoli.

Categorie ammesse: {categories}
Tipi di deal ammessi: {deal_types}

Rispondi SOLO con un oggetto JSON valido:
{{
  "headline": "string",
  "top_ranked": [{{"id": "id candidato", "category": "string", "tags": ["string"], "exploratory": false}}],
  "briefs": [{{"id": "id candidato", "category": "string", "one_liner": "string", "tags": ["string"]}}],
  "international": [{{"id": "id candidato", "category": "string", "one_liner": "string", "tags": ["string"]}}],
  "market_pill": {{"what_is_happening": "string", "for_you": "string", "watch": "string",
                  "stock_ideas": [{{"name": "string", "ticker": "string o null", "direction": "Acquisto", "rationale": "string", "risk": "string", "id": "id candidato"}}],
                  "ids": ["id candidato"]}},
  "deals": [{deal_schema}]
}}
"""

PROMPT_WRITE = """Scrivi le sintesi delle notizie di apertura del digest mattutino di un banker.

## Profilo del lettore
{profile}

## Istruzioni

Per ogni notizia trovi titolo, fonte e il TESTO dell'articolo letto in automatico.
- "summary": 2-3 frasi in italiano con i fatti chiave.
- "why_it_matters": 1-2 frasi dal punto di vista di un banker LevFin (sponsor, multipli, leva, chi finanzia, cosa dice sul mercato).
- "for_you": 1-2 frasi su cosa significa per il lettore in concreto e per il suo percorso (Leverage Finance, poi
  Londra/Parigi, poi buy side): un argomento da usare in un colloquio, un player o un tema da seguire, una competenza
  da allenare. Deve essere specifico; se il collegamento non c'è davvero, metti null.
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
  "top": [{{"id": "id", "summary": "string", "why_it_matters": "string", "for_you": "string o null", "verified": true, "original_url": "string o null"}}],
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


def build_write_prompt(picks: list[dict], profile: str = "") -> str:
    blocks = []
    for p in picks:
        body = p["text"] or "NON DISPONIBILE"
        url = p["resolved_url"] or p["url"]
        blocks.append(f"### [{p['id']}] {p['title']}\nFonte: {p['source']}\nURL: {url}\nTesto:\n{body}\n")
    return PROMPT_WRITE.format(items="\n".join(blocks), deal_schema=DEAL_SCHEMA, profile=profile.strip())


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
    if not ranked:
        raise ValueError("Claude non ha restituito notizie valide per la sezione top.")

    print("  Lettura articoli (Python, zero token)")
    read = []
    for e in ranked:
        c = by_id[e["id"]]
        art = articles.read(c)
        read.append({**c, "text": art["text"], "resolved_url": art["url"], "meta": e})
    # Nell'ordine di importanza, prima le notizie leggibili (numeri verificabili); le riserve
    # non leggibili entrano solo se non bastano quelle con testo.
    readable = [p for p in read if p["text"]]
    picks = (readable + [p for p in read if not p["text"]])[:TOP_N]
    picks.sort(key=lambda p: read.index(p))

    need_tools = any(p["text"] is None for p in picks)
    written = ask_claude(build_write_prompt(picks, profile), "scrittura", tools=need_tools, max_turns=15 if need_tools else 2)
    texts = {t.get("id"): t for t in written.get("top", [])}

    top = []
    for p in picks:
        t = texts.get(p["id"], {})
        top.append({
            **p["meta"],
            "summary": t.get("summary", ""), "why_it_matters": t.get("why_it_matters", ""),
            "for_you": t.get("for_you"), "verified": bool(t.get("verified")),
            "original_url": t.get("original_url") or p["resolved_url"],
        })

    deals = {d.get("id"): d for d in sel.get("deals", []) if d.get("id")}
    deals.update({d.get("id"): d for d in written.get("deals", []) if d.get("id")})  # i dati dal testo prevalgono
    return {"headline": sel.get("headline", ""), "top": top, "briefs": sel.get("briefs", []),
            "international": sel.get("international", []), "market_pill": sel.get("market_pill") or {},
            "deals": list(deals.values())}


def mock(candidates: list[dict]) -> dict:
    """Digest finto per provare sito e pipeline senza consumare il piano."""
    return {
        "headline": "Digest di prova (modalità mock): nessuna chiamata a Claude.",
        "top": [
            {"id": c["id"], "category": CATEGORIES[i % len(CATEGORIES)], "summary": "Testo di prova.",
             "why_it_matters": "Testo di prova.", "for_you": "Testo di prova." if i == 0 else None,
             "tags": ["test"], "verified": False,
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
        "market_pill": {"what_is_happening": "Testo di prova sui mercati.", "for_you": "Testo di prova.",
                        "watch": "Nessuna azione: prova.", "ids": [c["id"] for c in candidates[:2]]},
        "deals": [],
    }


def _deal_type(value):
    v = (value or "").strip()
    for t in DEAL_TYPES:
        if v.lower().startswith(t.lower()):
            return t
    return v or None


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
            fy = e.get("for_you")
            b.update(summary=e.get("summary", ""), why_it_matters=e.get("why_it_matters", ""),
                     for_you=fy if isinstance(fy, str) and fy.strip() and fy.strip().lower() != "null" else None,
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
            "deal_type": _deal_type(e.get("deal_type")), "sector": e.get("sector"), "country": e.get("country"),
            "ev_eur_m": _num(e.get("ev_eur_m")), "ev_ebitda": _num(e.get("ev_ebitda")),
            "leverage_x": _num(e.get("leverage_x")), "debt_package": e.get("debt_package"),
            "banks_advisors": e.get("banks_advisors"), "source": c["source"], "url": c["url"], "title": c["title"],
        })

    if not top:
        raise ValueError("Claude non ha restituito notizie valide per la sezione top.")
    mp = raw.get("market_pill") or {}
    pill = None
    if mp.get("what_is_happening"):
        pill = {k: str(mp.get(k) or "") for k in ("what_is_happening", "for_you", "watch")}
        pill["sources"] = [{"title": by_id[i]["title"], "source": by_id[i]["source"], "url": by_id[i]["url"]}
                           for i in mp.get("ids", []) if i in by_id][:4]
        pill["stock_ideas"] = []
        for idea in (mp.get("stock_ideas") or [])[:2]:
            if not isinstance(idea, dict) or not idea.get("name") or not idea.get("rationale"):
                continue
            c = by_id.get(idea.get("id"))
            direction = idea.get("direction") if idea.get("direction") in ("Acquisto", "Vendita", "Da monitorare") else "Da monitorare"
            pill["stock_ideas"].append({
                "name": str(idea["name"]), "ticker": idea.get("ticker") or None, "direction": direction,
                "rationale": str(idea["rationale"]), "risk": str(idea.get("risk") or ""),
                "url": c["url"] if c else None, "source": c["source"] if c else None,
            })
    return {"headline": raw.get("headline", ""), "top": top, "market_pill": pill, "briefs": briefs,
            "international": international, "deals": deals}
