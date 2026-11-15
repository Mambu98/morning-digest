"""Voti +/− dal sito: sincronizzazione da Cloudflare e riassunto per il prompt."""

from __future__ import annotations

import json
import os
import urllib.request
from collections import Counter
from datetime import date, timedelta
from pathlib import Path


def sync(path: Path) -> None:
    """Scarica i voti salvati su Cloudflare e li scrive in data/feedback.json.

    Se SITE_URL o FEEDBACK_TOKEN non sono configurati, non fa nulla (si usa il file esistente).
    """
    site_url = os.environ.get("SITE_URL", "").rstrip("/")
    token = os.environ.get("FEEDBACK_TOKEN", "")
    if not site_url or not token:
        print("  feedback: SITE_URL/FEEDBACK_TOKEN non configurati, salto la sincronizzazione")
        return
    req = urllib.request.Request(
        f"{site_url}/api/votes",
        headers={"Authorization": f"Bearer {token}", "User-Agent": "morning-digest"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            votes = json.load(resp)
    except Exception as exc:  # il digest deve uscire anche se i voti non sono raggiungibili
        print(f"  ! feedback non scaricato: {exc}")
        return
    votes.sort(key=lambda v: (v.get("date", ""), v.get("id", "")))
    path.write_text(json.dumps(votes, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  feedback: {len(votes)} voti sincronizzati")


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def summary(votes: list[dict], today: date, days: int = 60) -> str:
    """Testo compatto da inserire nel prompt."""
    since = (today - timedelta(days=days)).isoformat()
    recent = [v for v in votes if v.get("date", "") >= since and v.get("vote") in (1, -1)]
    if not recent:
        return "Nessun voto ancora: usa solo il profilo."

    def counts(field: str) -> str:
        up, down = Counter(), Counter()
        for v in recent:
            (up if v["vote"] == 1 else down)[v.get(field) or "n/d"] += 1
        keys = sorted(set(up) | set(down), key=lambda k: -(up[k] - down[k]))
        return ", ".join(f"{k} (+{up[k]}/−{down[k]})" for k in keys)

    liked = [v for v in recent if v["vote"] == 1][-15:]
    disliked = [v for v in recent if v["vote"] == -1][-15:]
    lines = [
        f"Voti degli ultimi {days} giorni: {len(liked)} positivi, {len(disliked)} negativi (mostrati gli ultimi).",
        f"Per categoria: {counts('category')}",
        f"Per fonte: {counts('source')}",
        "Notizie apprezzate (+):",
        *[f"  + {v.get('title', '')} [{v.get('category', '')}, {v.get('source', '')}]" for v in liked],
        "Notizie non apprezzate (−):",
        *[f"  − {v.get('title', '')} [{v.get('category', '')}, {v.get('source', '')}]" for v in disliked],
    ]
    return "\n".join(lines)
