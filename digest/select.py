"""Selezione e sintesi con Claude Code (headless, piano Pro via CLAUDE_CODE_OAUTH_TOKEN)."""

from __future__ import annotations

import json
import os
import subprocess

CATEGORIES = ["LBO / PE Italia", "LevFin & Private credit", "Fondi PE", "M&A Italia", "Piazza Affari / EGM", "Macro & Mercati"]
DEAL_TYPES = ["LBO", "Secondary buyout", "Add-on", "M&A", "Minoranza", "Exit", "Financing", "Refinancing", "Fundraising", "IPO", "OPA / Delisting"]
MODEL = os.environ.get("DIGEST_MODEL", "sonnet")

PROMPT = """Sei il redattore del digest mattutino personale di un banker. Data di oggi: {date}.

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

## Compito
1. Scegli le 3 notizie più rilevanti per il lettore (campo "top"), seguendo le priorità del profilo e pesando il feedback.
   Una delle 3 può essere "esplorativa" (fuori dalle preferenze recenti ma importante): segnala con "exploratory": true.
2. Per ciascuna delle 3, leggi la notizia sulla fonte originale (massimo 3 chiamate per notizia).
   I link dei candidati sono redirect di Google News e NON sono leggibili: cerca il titolo con WebSearch,
   poi apri l'articolo originale (o un articolo equivalente di una fonte autorevole) con WebFetch.
   - "summary": 2-3 frasi in italiano con i fatti chiave.
   - "why_it_matters": 1-2 frasi dal punto di vista di un banker LevFin / structured lending (sponsor, multipli, leva, chi finanzia, cosa dice sul mercato).
   - Numeri (EV, multipli, leva, importi) SOLO se letti nella fonte. Mai stimare o dedurre.
   - "verified": true se hai letto la fonte, false se hai potuto usare solo il titolo (in quel caso limita il summary ai fatti del titolo).
   - "original_url": URL della fonte originale che hai letto, se lo hai trovato (altrimenti null).
3. Scegli altre 6-8 notizie per "briefs", con "one_liner" in italiano di massimo 25 parole basato sul titolo.
4. Evita doppioni: se la stessa notizia compare da più fonti, scegline una sola.
5. "deals": estrai TUTTE le operazioni (anche non selezionate sopra) presenti tra i candidati: M&A, LBO, financing, fundraising, IPO, OPA.
   Compila i campi solo con informazioni esplicite (titolo o fonte letta); altrimenti null. Mai stimare.
6. "headline": una frase in italiano che sintetizza il tema della giornata.

Categorie ammesse: {categories}
Tipi di deal ammessi: {deal_types}

## Output
Rispondi SOLO con un oggetto JSON valido, senza testo prima o dopo, con questo schema:
{{
  "headline": "string",
  "top": [{{"id": "id candidato", "category": "string", "summary": "string", "why_it_matters": "string", "tags": ["string"], "verified": true, "exploratory": false, "original_url": "string o null"}}],
  "briefs": [{{"id": "id candidato", "category": "string", "one_liner": "string", "tags": ["string"]}}],
  "deals": [{{"id": "id candidato", "target": "string", "buyer": "string o null", "seller": "string o null", "deal_type": "string", "sector": "string o null", "country": "string o null", "ev_eur_m": "numero o null", "ev_ebitda": "numero o null", "leverage_x": "numero o null", "debt_package": "string o null", "banks_advisors": "string o null"}}]
}}
"""


def build_prompt(candidates: list[dict], profile: str, feedback: str, date: str, preferred: list[str] = ()) -> str:
    lines = [
        f"[{c['id']}] {(c['published'] or '')[:10]} | {c['source']} | {c['topic']} | {c['title']}" for c in candidates
    ]
    return PROMPT.format(
        date=date,
        profile=profile.strip(),
        feedback=feedback,
        preferred=", ".join(preferred) or "nessuna indicazione",
        candidates="\n".join(lines),
        categories=", ".join(CATEGORIES),
        deal_types=", ".join(DEAL_TYPES),
    )


def _extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"Nessun JSON nella risposta di Claude:\n{text[:2000]}")
    return json.loads(text[start : end + 1])


def ask_claude(prompt: str) -> dict:
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--model", MODEL,
        "--max-turns", "30",
        "--allowedTools", "WebSearch", "WebFetch",  # deve restare l'ultima opzione (accetta più valori)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    if res.returncode != 0:
        raise RuntimeError(f"Claude Code ha restituito un errore ({res.returncode}):\n{res.stderr[-3000:]}\n{res.stdout[-3000:]}")
    envelope = json.loads(res.stdout)
    denials = envelope.get("permission_denials") or []
    print(f"  Claude: {envelope.get('num_turns')} turni, {round((envelope.get('duration_ms') or 0) / 1000)}s, "
          f"permessi negati: {len(denials)}")
    for d in denials[:5]:
        print(f"    negato: {d.get('tool_name')}")
    if envelope.get("is_error"):
        raise RuntimeError(f"Claude Code: {envelope.get('result') or envelope}")
    return _extract_json(envelope.get("result", ""))


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
    for e in raw.get("top", [])[:3]:
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
    return {"headline": raw.get("headline", ""), "top": top, "briefs": briefs, "deals": deals}
