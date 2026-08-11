"""Generate a synthetic sample dataset for pipeline smoke tests.

IMPORTANT (FACT): This data is synthetic. Niche winners from sample runs are NOT
empirical evidence. Use only to validate code paths.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone

from cartoon_niche_radar.models.schemas import MadeForKids, Platform, ShortOrLong, VideoRecord
from cartoon_niche_radar.storage.export import write_jsonl
from cartoon_niche_radar.utils.config import get_taxonomy, project_paths
from cartoon_niche_radar.utils.epochs import classify_views_metric_epoch
from cartoon_niche_radar.utils.time import age_days, channel_size_bucket, safe_div, utcnow


def generate_sample(n: int = 500, seed: int = 42) -> list[VideoRecord]:
    rng = random.Random(seed)
    tax = get_taxonomy()
    ages = [a["id"] for a in tax["age_clusters"]]
    themes = [t for t in tax["themes"] if t != "other"]
    styles = [s for s in tax["visual_styles"] if s != "unknown"]

    records: list[VideoRecord] = []
    now = utcnow()
    break_dt = datetime(2025, 3, 31, tzinfo=timezone.utc)
    for i in range(n):
        age = rng.choice(ages)
        theme = rng.choice(themes)
        style = rng.choice(styles)
        duration = rng.choice([12, 18, 25, 35, 45, 58, 90])
        # ~80% POST-break Shorts era, ~20% PRE — to exercise epoch separation
        if rng.random() < 0.2:
            publish = break_dt - timedelta(days=rng.randint(1, 200))
        else:
            publish = break_dt + timedelta(days=rng.randint(1, 400))
            if publish > now:
                publish = now - timedelta(days=rng.randint(1, 60))
        subs = rng.choice([500, 5_000, 25_000, 250_000, 2_000_000])
        base = rng.lognormvariate(8, 1.2)
        views = int(base * (1 + subs / 1_000_000))
        likes = int(views * rng.uniform(0.02, 0.08))
        comments = int(views * rng.uniform(0.001, 0.01))
        title = (
            f"{theme.replace('_', ' ')} cartoon short for age {age} "
            f"{style.replace('_', ' ')} #{i}"
        )
        age_kw = {
            "2-5": "preschool toddler kids cartoon",
            "6-8": "children elementary kids animation",
            "9-12": "tween middle school cartoon adventure",
            "13-17": "teenager high school teen cartoon",
            "18-24": "adult animation workplace general audience",
        }[age]
        desc = (
            f"Animated story about {theme}. {age_kw}. "
            f"{'episode series' if rng.random() < 0.3 else 'one shot'}"
        )
        days = age_days(publish, now)
        short_or_long = ShortOrLong.SHORT if duration <= 60 else ShortOrLong.LONG
        epoch = classify_views_metric_epoch(
            publish_date=publish, short_or_long=short_or_long.value
        )
        # FACT field — independent of estimated age inference
        if age in {"2-5", "6-8"} and rng.random() < 0.7:
            mfk = MadeForKids.TRUE
        elif age in {"18-24"} and rng.random() < 0.7:
            mfk = MadeForKids.FALSE
        else:
            mfk = rng.choice([MadeForKids.TRUE, MadeForKids.FALSE, MadeForKids.UNKNOWN])

        records.append(
            VideoRecord(
                video_id=f"synth_{i:05d}",
                channel_id=f"ch_{rng.randint(1, max(20, n // 10))}",
                platform=Platform.YOUTUBE,
                title=title,
                description=desc,
                publish_date=publish,
                duration_seconds=duration,
                views=views,
                likes=likes,
                comments=comments,
                views_per_day=safe_div(views, days),
                channel_subscribers=subs,
                video_count=rng.randint(10, 500),
                language=rng.choice(["en", "en", "en", "es", "pt", "hi"]),
                country=rng.choice(["US", "GB", "IN", "BR", None]),
                short_or_long=short_or_long,
                made_for_kids=mfk,
                views_metric_epoch=epoch.value,
                channel_size_bucket=channel_size_bucket(subs),
                collected_at=now,
                source="synthetic_sample",
            )
        )

    paths = project_paths()
    write_jsonl(
        paths["raw"] / "youtube_videos.jsonl",
        [r.model_dump(mode="json") for r in records],
    )
    meta = {
        "status": "synthetic",
        "n": n,
        "WARNING": "SYNTHETIC DATA — not empirical. Do not use for niche conclusions.",
        "kind": "UNKNOWN_as_market_evidence",
    }
    (paths["raw"] / "collect_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return records
