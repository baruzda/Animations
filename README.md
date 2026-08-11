# CARTOON NICHE RADAR

Empirical research pipeline to identify which **age audiences × themes × visual styles × formats** of short-form AI animation maximize commercial opportunity on YouTube Shorts (primary), with optional TikTok / Instagram signals.

Core objective metric:

```text
Views × Growth Velocity × Engagement × Monetization Potential / Competition
```

Implemented as configurable **OPPORTUNITY SCORE** (see `cartoon_niche_radar/config/scoring.yaml`).

## Production workspaces

В этом же репозитории отдельно хранится производственная память мультсериалов:

- `technical/` — общая техническая часть производства для всех сериалов;
- `series/` — отдельная творческая папка на каждый сериал;
- `series/Бойся своих желаний/` — первый активный сериал.

Исследовательский слой `cartoon_niche_radar/` и творческий канон сериалов не смешиваются: исследование помогает принимать решения, но не переписывает канон автоматически.

## Epistemic rules

Every analytical claim is tagged:

| Kind | Meaning |
|------|---------|
| **FACT** | Directly observed from an API / file (e.g. YouTube `viewCount`) |
| **INFERENCE** | Derived model/heuristic with confidence |
| **UNKNOWN** | Insufficient evidence — never invented |

Low-confidence AI labels become **UNKNOWN**, not guesses.

Bias guard: age **13–17** is a watched hypothesis, not a preferred conclusion. Control group **18–24** remains visible. Winners are **not declared** when evidence gates fail.

## Phases

1. **Sources** — YouTube Data API v3 (primary); yt-dlp enrichment; Google Trends (secondary); TikTok public / Instaloader experimental & off by default.
2. **Dataset** — ≥10 000 relevant videos target; schema in `models/schemas.py`.
3. **Normalization** — `views/day`, `views/subscriber`, engagement/like/comment rates, viral coefficient, channel-size adjusted performance; buckets `<10k / 10k–100k / 100k–1m / 1m+`.
4. **Classification** — age, theme, story, hook, style, character, emotion, format, series potential + confidence.
5. **Commercial score** — Demand, Viral, Competition, Production Complexity, Monetization, IP Potential, Localization → Opportunity.
6. **Output** — CSV/JSON + 12 reports + TOP-20 niches + highlights (`MOST VIEWS`, `BEST MONEY`, `EASIEST TO ENTER`, `BEST FOR AI PRODUCTION`, `BEST OVERALL`).

## Source policy (FACT)

- **TikTok Research API is not used.** Current TikTok Research Tools terms prohibit commercial use; commercial users are ineligible. See `config/sources.yaml`.
- Google Trends is a **secondary demand signal only**, never monetization proof.
- No commenter PII / comment text storage (aggregate counts only).

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,dashboard]"

cp .env.example .env
# set YOUTUBE_API_KEY=...

# Smoke-test pipeline on synthetic data (NOT empirical):
cnr run-all --use-sample --stage A

# Staged live protocol (multi-day, resume-safe) — do NOT jump to 10k:
cnr collect --stage A          # 500 — QA
cnr collect --stage B          # 2000 — bias check
cnr collect --stage C          # 10000+ — main analysis

# Split discovery vs enrichment if needed:
cnr collect --discover-only --stage A
cnr collect --enrich-only

cnr normalize && cnr classify && cnr score && cnr report

# Dashboard:
streamlit run cartoon_niche_radar/dashboard/app.py
```

### Quota model (June 2026+)

Config: `cartoon_niche_radar/config/quota.yaml`

| Bucket | Endpoints | Default daily limit |
|--------|-----------|---------------------|
| SEARCH | `search.list` | 100 calls |
| BATCH_STATS | `videos.batchGetStats` | 10_000 |
| GENERAL | other methods | 10_000 units |

Reset: midnight Pacific Time. Collector stops **before** exceeding any bucket.

## Outputs

| Path | Contents |
|------|----------|
| `data/raw/` | Collected videos + source meta |
| `data/normalized/` | Normalized metrics CSV/JSONL |
| `data/classified/` | Classifications with confidence |
| `data/scored/` | Niche component + opportunity scores |
| `data/reports/SUMMARY.md` | Human-readable report |
| `data/reports/top20_niches.csv` | TOP-20 niche cards |
| `data/reports/highlights.json` | MOST VIEWS / MONEY / EASIEST / AI / OVERALL |

## Config knobs

- `config/scoring.yaml` — opportunity weights + evidence gates
- `config/taxonomy.yaml` — ages, themes, styles
- `config/collection.yaml` — query grid, Shorts filters, 10k target
- `config/sources.yaml` — enable/disable sources

## Project layout

```text
cartoon_niche_radar/
  collectors/     # YouTube, yt-dlp, TikTok stub, IG stub, Trends
  pipeline/       # collect → normalize → classify → score → report
  models/         # schemas + Evidenced[FACT|INFERENCE|UNKNOWN]
  storage/        # SQLite + CSV/JSON export
  dashboard/      # Streamlit UI
  config/         # YAML configs
```

## License

MIT
