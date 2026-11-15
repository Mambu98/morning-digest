"""Entry point: python -m digest.run  (DIGEST_MOCK=1 per una prova senza Claude)."""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import feedback, fetch, select, site

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DEAL_FIELDS = ["date", "target", "buyer", "seller", "deal_type", "sector", "country", "ev_eur_m", "ev_ebitda",
               "leverage_x", "debt_package", "banks_advisors", "source", "url", "title"]


def _norm(s: str | None) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def append_deals(deals: list[dict], path: Path) -> int:
    """Aggiunge i deal nuovi al database CSV (dedup su target + tipo)."""
    existing: set[tuple[str, str]] = set()
    if path.exists():
        with path.open(encoding="utf-8", newline="") as f:
            existing = {(_norm(r["target"]), _norm(r["deal_type"])) for r in csv.DictReader(f)}
    new = [d for d in deals if (_norm(d["target"]), _norm(d["deal_type"])) not in existing]
    if not new:
        return 0
    write_header = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DEAL_FIELDS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerows(new)
    return len(new)


def main() -> None:
    today = datetime.now(ZoneInfo("Europe/Rome")).date()
    day = today.isoformat()
    (DATA / "digests").mkdir(parents=True, exist_ok=True)

    print("1/4 Feedback")
    feedback.sync(DATA / "feedback.json")
    fb_text = feedback.summary(feedback.load(DATA / "feedback.json"), today)

    print("2/4 Raccolta notizie")
    candidates = fetch.collect(ROOT / "config" / "sources.toml")
    (DATA / "candidates_latest.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  {len(candidates)} candidati unici")
    if len(candidates) < 5:
        raise SystemExit("Troppo pochi candidati: controlla le fonti in config/sources.toml")

    print("3/4 Selezione con Claude")
    if os.environ.get("DIGEST_MOCK") == "1":
        raw = select.mock(candidates)
    else:
        profile = (ROOT / "config" / "profile.md").read_text(encoding="utf-8")
        raw = select.ask_claude(select.build_prompt(candidates, profile, fb_text, day))
    digest = select.validate(raw, candidates)
    digest["date"] = day
    (DATA / "digests" / f"{day}.json").write_text(json.dumps(digest, ensure_ascii=False, indent=1), encoding="utf-8")
    added = append_deals(digest["deals"], DATA / "deals.csv")
    print(f"  top {len(digest['top'])}, brevi {len(digest['briefs'])}, deal nuovi nel database {added}")

    print("4/4 Sito")
    site.build_all(DATA / "digests", ROOT / "site")
    print("Fatto.")


if __name__ == "__main__":
    main()
