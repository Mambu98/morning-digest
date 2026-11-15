"""Lettura degli articoli in Python (zero token): risolve i link di Google News ed estrae il testo."""

from __future__ import annotations

import urllib.error
import urllib.request
from urllib.parse import urlparse

MIN_CHARS = 600      # sotto questa soglia è quasi sempre un paywall o un teaser
MAX_CHARS = 7000     # testo passato a Claude per articolo
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}


def resolve(url: str) -> str:
    """Converte un link redirect di Google News nell'URL originale dell'articolo."""
    if "news.google.com" not in url:
        return url
    try:
        from googlenewsdecoder import gnewsdecoder

        res = gnewsdecoder(url, interval=1)
        if res.get("status") and res.get("decoded_url"):
            return res["decoded_url"]
        print(f"    ! decodifica Google News non riuscita: {res.get('message')}")
    except Exception as exc:
        print(f"    ! decodifica Google News fallita: {exc}")
    return url


def _download(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def text(url: str) -> tuple[str | None, str]:
    """(testo, motivo): testo principale dell'articolo o None con il motivo del fallimento."""
    if "news.google.com" in url:
        return None, "link Google News non decodificato"
    try:
        import trafilatura

        html = _download(url)
        body = trafilatura.extract(html, url=url, include_comments=False, include_tables=True)
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except Exception as exc:
        return None, f"errore {type(exc).__name__}"
    if not body:
        return None, "nessun testo estratto"
    if len(body) < MIN_CHARS:
        return None, f"testo breve ({len(body)} caratteri, probabile paywall)"
    return body[:MAX_CHARS], f"{len(body)} caratteri"


def read(candidate: dict) -> dict:
    """Restituisce {'url': URL originale o None, 'text': testo o None}."""
    original = resolve(candidate["url"])
    body, reason = text(original)
    print(f"    {candidate['source']} ({urlparse(original).netloc}): {reason}")
    return {"url": original if original != candidate["url"] else None, "text": body}
