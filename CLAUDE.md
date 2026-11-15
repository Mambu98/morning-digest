# morning-digest: istruzioni per Claude

Digest mattutino personale di Francesco (LevFin, PE, private credit, M&A Italia, macro).

## Come funziona
- `.github/workflows/digest.yml` gira ogni mattina su GitHub Actions ed esegue `python -m digest.run`.
- `digest/fetch.py` raccoglie i candidati da Google News/RSS (fonti in `config/sources.toml`): nessun token.
- `digest/select.py` chiama Claude Code headless (`claude -p`, piano Pro via secret `CLAUDE_CODE_OAUTH_TOKEN`) per scegliere 3 top + brevi ed estrarre i deal.
- `digest/site.py` genera il sito statico in `site/`; Cloudflare Pages lo pubblica a ogni push.
- `functions/api/` sono le Cloudflare Pages Functions per i voti +/− (KV binding `VOTES`, secret `FEEDBACK_TOKEN`).
- Dati: `data/digests/YYYY-MM-DD.json`, `data/deals.csv` (database deal), `data/feedback.json` (snapshot voti).

## Regole
- Lingua: italiano per testi e commenti; terminologia finance in inglese.
- Numeri (EV, multipli, leva) solo se presenti nella fonte: mai stime o deduzioni.
- Solo dati pubblici e personali: mai informazioni, clienti o documenti della banca.
- Per provare senza consumare il piano: `DIGEST_MOCK=1 python -m digest.run`.
- Il profilo del lettore è in `config/profile.md`: è il primo posto dove intervenire per cambiare la selezione.
