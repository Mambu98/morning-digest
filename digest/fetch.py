"""Raccolta delle notizie candidate da Google News e feed RSS. Nessun token consumato."""

from __future__ import annotations

import calendar
import hashlib
import re
import tomllib
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser

GOOGLE_NEWS = "https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"
LOCALES = {
    "it": ("it", "IT", "IT:it"),
    "en": ("en-GB", "GB", "GB:en"),
}
USER_AGENT = "Mozilla/5.0 (morning-digest; personal use)"


def item_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]


def _dedup_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())[:70]


def _published(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)


def _clean_title(title: str, source: str) -> str:
    # Google News aggiunge " - Nome Testata" in coda al titolo
    if source and title.endswith(f" - {source}"):
        return title[: -len(source) - 3].strip()
    return title.strip()


def _entries(url: str):
    feed = feedparser.parse(url, agent=USER_AGENT)
    if feed.bozo and not feed.entries:
        print(f"  ! feed non leggibile: {url} ({feed.get('bozo_exception')})")
    return feed.entries


def collect(config_path: Path, max_age_hours: int = 36, per_query: int = 15, limit: int = 150) -> list[dict]:
    cfg = tomllib.loads(config_path.read_text(encoding="utf-8"))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    blocked = [b.lower() for b in cfg.get("filters", {}).get("blocked_sources", [])]
    seen: set[str] = set()
    items: list[dict] = []

    def add(entry, topic: str, default_source: str = "") -> None:
        url = entry.get("link", "")
        source = (entry.get("source") or {}).get("title", "") or default_source
        title = _clean_title(entry.get("title", ""), source)
        published = _published(entry)
        if not url or not title:
            return
        if any(b in source.lower() for b in blocked):
            return
        if published and published < cutoff:
            return
        key = _dedup_key(title)
        if key in seen:
            return
        seen.add(key)
        items.append(
            {
                "id": item_id(url),
                "title": title,
                "source": source,
                "url": url,
                "published": published.isoformat() if published else None,
                "topic": topic,
            }
        )

    for q in cfg.get("google_news", []):
        hl, gl, ceid = LOCALES[q.get("lang", "it")]
        url = GOOGLE_NEWS.format(q=urllib.parse.quote(f"{q['q']} when:2d"), hl=hl, gl=gl, ceid=ceid)
        entries = _entries(url)
        print(f"  {q.get('topic', q['q'])}: {len(entries)} risultati")
        for entry in entries[:per_query]:
            add(entry, q.get("topic", ""))

    for feed in cfg.get("rss", []):
        entries = _entries(feed["url"])
        print(f"  {feed.get('topic', feed['url'])}: {len(entries)} risultati")
        for entry in entries[:per_query]:
            add(entry, feed.get("topic", ""), feed.get("source", ""))

    items.sort(key=lambda i: i["published"] or "", reverse=True)
    return items[:limit]
