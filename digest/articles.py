"""Lettura degli articoli in Python (zero token): risolve i link di Google News ed estrae il testo."""

from __future__ import annotations

MIN_CHARS = 600      # sotto questa soglia è quasi sempre un paywall o un teaser
MAX_CHARS = 7000     # testo passato a Claude per articolo


def resolve(url: str) -> str:
    """Converte un link redirect di Google News nell'URL originale dell'articolo."""
    if "news.google.com" not in url:
        return url
    try:
        from googlenewsdecoder import gnewsdecoder

        res = gnewsdecoder(url, interval=1)
        if res.get("status") and res.get("decoded_url"):
            return res["decoded_url"]
    except Exception as exc:
        print(f"    ! decodifica Google News fallita: {exc}")
    return url


def text(url: str) -> str | None:
    """Testo principale dell'articolo, o None se non leggibile (paywall, blocco, errore)."""
    if "news.google.com" in url:
        return None
    try:
        import trafilatura

        html = trafilatura.fetch_url(url)
        if not html:
            return None
        body = trafilatura.extract(html, include_comments=False, include_tables=True, favor_precision=True)
    except Exception as exc:
        print(f"    ! lettura fallita {url}: {exc}")
        return None
    if not body or len(body) < MIN_CHARS:
        return None
    return body[:MAX_CHARS]


def read(candidate: dict) -> dict:
    """Restituisce {'url': URL originale, 'text': testo o None}."""
    original = resolve(candidate["url"])
    body = text(original)
    status = f"{len(body)} caratteri" if body else "non leggibile"
    print(f"    {candidate['source']}: {status}")
    return {"url": original if original != candidate["url"] else None, "text": body}
