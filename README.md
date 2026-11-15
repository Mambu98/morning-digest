# Morning digest

Ogni mattina, prima delle 8: le 3 notizie più importanti su LevFin, private equity, private credit, M&A Italia e macro, più le brevi e un deal tracker. Sul sito ogni notizia ha i bottoni **+ / −**: i voti rientrano nel prompt del giorno dopo e la selezione si affina nel tempo.

## Come funziona

1. **GitHub Actions** (cloud, anche a PC spento) parte alle 05:30 UTC.
2. **Python** raccoglie le notizie da Google News e feed RSS (`config/sources.toml`), toglie i doppioni. Zero token.
3. **Claude Code** (piano Pro) sceglie le 3 top leggendo le fonti originali, scrive le sintesi ed estrae i deal in forma strutturata.
4. **Python** genera il sito (`site/`) e aggiorna il database deal (`data/deals.csv`).
5. **Cloudflare Pages** pubblica il sito a ogni aggiornamento e salva i voti +/−.

## Cosa modificare

| Voglio... | File |
|---|---|
| cambiare interessi e priorità | `config/profile.md` |
| aggiungere o togliere fonti | `config/sources.toml` |
| cambiare l'orario | `cron` in `.github/workflows/digest.yml` (orario UTC) |

## Lanciarlo a mano
GitHub → **Actions** → **Morning digest** → **Run workflow**. Spunta "mock" per una prova senza usare Claude.

## Setup (una volta sola)

**GitHub**
- Secret `CLAUDE_CODE_OAUTH_TOKEN`: generato con `claude setup-token` sul Mac.
- Secret `FEEDBACK_TOKEN`: una password lunga a piacere (la stessa va su Cloudflare).
- Variable `SITE_URL`: l'indirizzo del sito Cloudflare, es. `https://morning-digest.pages.dev`.
  (Settings → Secrets and variables → Actions → tab *Secrets* / *Variables*)

**Cloudflare**
- Workers & Pages → Create → Pages → collega il repo `morning-digest`.
  Framework preset: *None*, build command: vuoto, build output directory: `site`.
- Storage → KV → crea il namespace `morning-digest-votes`.
- Nel progetto Pages → Settings → Bindings → KV namespace: nome variabile `VOTES` → `morning-digest-votes`.
- Nel progetto Pages → Settings → Variables and secrets: secret `FEEDBACK_TOKEN` (stessa password di GitHub).
- Rilancia il deploy dopo aver aggiunto binding e secret.

## Regole
Solo fonti pubbliche e account personali. Nessun dato della banca entra in questo repo.
