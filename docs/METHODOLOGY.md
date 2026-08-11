# Methodology — CARTOON NICHE RADAR

## Research question

Which segment of short-form AI / cartoon animation maximizes:

```text
Views × Growth Velocity × Engagement × Monetization Potential / Competition
```

across YouTube Shorts (primary), with TikTok / Reels as secondary when legally collectible.

## What counts as evidence

### FACT
- Platform statistics returned by APIs (views, likes, comments, duration, publish time, subscriber counts when provided).
- Explicit config / ToS constraints (e.g. TikTok Research API commercial prohibition).

### INFERENCE
- Target age, theme, visual style, hook, emotional trigger from title/description/model.
- Opportunity score and component scores.
- RPM / monetization proxies (not measured ad revenue).
- “Viral coefficient” and channel-size adjusted performance formulas.

### UNKNOWN
- Any label below `min_confidence_for_label`.
- Platform data not collected (disabled TikTok/IG).
- True RPM, brand deal rates, completion rate (not in YouTube Data API).
- Causal claims (“theme X causes virality”).

## Why not raw views

Older videos accumulate more absolute views. Primary comparison metric is **views/day** (and related normalized rates). Raw views may appear in descriptive tables but are not the ranking basis.

## Channel-size lens

Niches are examined within subscriber buckets:

- micro `<10k`
- small `10k–100k`
- mid `100k–1m`
- mega `1m+`

Breakthrough analysis privileges micro/small outperformance so “only mega channels win” niches are not mistaken for new-entrant opportunities.

## Evidence gates

Configured in `scoring.yaml`. If unmet:

- `opportunity_score` for a niche is withheld (`null`)
- highlights (`BEST_OVERALL`, etc.) are set to `null` / `INSUFFICIENT_DATA`
- reports still emit descriptive aggregations with explicit kind tags

Default gates (tunable):

- ≥1000 videos in the working sample to declare global winners
- ≥30 videos and ≥5 channels per niche
- median classification confidence ≥0.55

## Bias guard (13–17)

The project must not “aim” at teen niches. Age 13–17 is listed as a **watched hypothesis**. All age clusters including 18–24 control are scored with the same formulas. Preferential weighting by age ID is forbidden in config (`bias_guards`).

## TikTok / Instagram

- Research API: **blocked** for this commercial research design.
- Unofficial public scrapers: optional, default off, require explicit enable + legal review.
- Absence of TikTok/IG rows is recorded as UNKNOWN coverage, not as “TikTok has no opportunity”.

## Shorts view-count structural break (FACT)

On **2025-03-31** YouTube changed Shorts view counting.

Each video stores `views_metric_epoch`:

- `PRE_2025_03_31`
- `POST_2025_03_31`
- `NON_SHORT`
- `UNKNOWN`

Primary Opportunity analysis for Shorts uses **POST_2025_03_31 only**.
PRE-epoch metrics are exported separately and must not be mixed into median views/day
or viral scores for opportunity ranking.

## madeForKids vs estimated age

- `made_for_kids` from `status.madeForKids` = **FACT** (`true` / `false` / `unknown`)
- `estimated_target_age` = **INFERENCE** with confidence, classifier_version, evidence features
- Never derive a specific age band solely from madeForKids

## Granular quota (June 2026+)

Separate buckets (config: `quota.yaml`):

- `SEARCH` — `search.list` (~100 calls/day)
- `BATCH_STATS` — `videos.batchGetStats` (~10_000/day)
- `GENERAL` — remaining methods (~10_000 units/day)

Reset: midnight Pacific Time. Collector stops **before** exceed. Multi-day resume is required for 10k.

## Staged live protocol

- Stage A: 500 — pipeline/data-quality QA
- Stage B: 2000 — sampling/bias QA
- Stage C: 10000+ — main analysis

Do not start at 10k on day one.

