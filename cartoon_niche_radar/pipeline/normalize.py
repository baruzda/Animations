from __future__ import annotations

from typing import Iterable, List, Optional

import pandas as pd

from cartoon_niche_radar.models.schemas import ChannelSizeBucket, NormalizedMetrics, VideoRecord
from cartoon_niche_radar.storage.export import write_csv, write_jsonl
from cartoon_niche_radar.utils.config import get_collection_config, get_scoring_config, project_paths
from cartoon_niche_radar.utils.epochs import ViewsMetricEpoch, classify_views_metric_epoch
from cartoon_niche_radar.utils.time import age_days, channel_size_bucket, safe_div


def normalize_record(rec: VideoRecord) -> NormalizedMetrics:
    """Phase 3 — never compare raw views across different ages as primary metric."""
    days = age_days(rec.publish_date)
    views = rec.views
    likes = rec.likes
    comments = rec.comments
    subs = rec.channel_subscribers

    epoch = rec.views_metric_epoch or classify_views_metric_epoch(
        publish_date=rec.publish_date,
        short_or_long=rec.short_or_long.value
        if hasattr(rec.short_or_long, "value")
        else rec.short_or_long,
    )
    if hasattr(epoch, "value"):
        epoch_value = epoch.value
    else:
        epoch_value = str(epoch)

    primary_epoch = (
        get_scoring_config()
        .get("normalization", {})
        .get("shorts_opportunity_epoch", ViewsMetricEpoch.POST_2025_03_31.value)
    )
    # Opportunity-eligible: POST epoch Shorts, or NON_SHORT (longform control), never PRE mixed in
    opportunity_eligible = epoch_value in {
        primary_epoch,
        ViewsMetricEpoch.NON_SHORT.value,
    }

    # Do not compute viral/views_per_day contribution for PRE Shorts into opportunity path
    views_per_day = safe_div(views, days)
    views_per_sub = safe_div(views, subs)
    engagement = safe_div((likes or 0) + (comments or 0), views)
    like_rate = safe_div(likes, views)
    comment_rate = safe_div(comments, views)

    viral = None
    if (
        opportunity_eligible
        and engagement is not None
        and views_per_day is not None
    ):
        size_norm = 1.0
        if subs and subs > 0:
            size_norm = 1.0 / (1.0 + (subs / 100_000.0))
        viral = engagement * views_per_day * size_norm

    bucket_str = rec.channel_size_bucket or channel_size_bucket(subs)
    try:
        bucket = ChannelSizeBucket(bucket_str)
    except ValueError:
        bucket = ChannelSizeBucket.UNKNOWN

    adjusted = None
    if opportunity_eligible and views_per_day is not None:
        denom = 1.0
        if subs and subs > 0:
            denom = max(1.0, (subs ** 0.5) / 100.0)
        adjusted = views_per_day / denom

    return NormalizedMetrics(
        video_id=rec.video_id,
        views_per_day=views_per_day,
        views_per_subscriber=views_per_sub,
        engagement_rate=engagement,
        like_rate=like_rate,
        comment_rate=comment_rate,
        viral_coefficient=viral,
        channel_size_bucket=bucket,
        channel_size_adjusted_performance=adjusted,
        age_days=days,
        views_metric_epoch=epoch_value,
        opportunity_eligible=opportunity_eligible,
    )


def normalize_many(records: Iterable[VideoRecord]) -> pd.DataFrame:
    rows = [normalize_record(r).model_dump(mode="json") for r in records]
    return pd.DataFrame(rows)


def run_normalize(records: Optional[List[VideoRecord]] = None) -> pd.DataFrame:
    paths = project_paths()
    if records is None:
        raw = paths["raw"] / "youtube_videos.jsonl"
        if not raw.exists():
            raise FileNotFoundError(f"Missing {raw}; run collect first.")
        import orjson

        records = []
        with raw.open("rb") as f:
            for line in f:
                records.append(VideoRecord.model_validate(orjson.loads(line)))

    df = normalize_many(records)
    write_jsonl(paths["normalized"] / "metrics.jsonl", df.to_dict(orient="records"))
    write_csv(paths["normalized"] / "metrics.csv", df.to_dict(orient="records"))

    base = pd.DataFrame(
        [
            {
                "video_id": r.video_id,
                "channel_id": r.channel_id,
                "title": r.title,
                "publish_date": r.publish_date.isoformat() if r.publish_date else None,
                "duration_seconds": r.duration_seconds,
                "views": r.views,
                "likes": r.likes,
                "comments": r.comments,
                "channel_subscribers": r.channel_subscribers,
                "language": r.language,
                "country": r.country,
                "short_or_long": r.short_or_long.value
                if hasattr(r.short_or_long, "value")
                else r.short_or_long,
                "made_for_kids": r.made_for_kids.value
                if hasattr(r.made_for_kids, "value")
                else r.made_for_kids,
                "views_metric_epoch": r.views_metric_epoch,
            }
            for r in records
        ]
    )
    merged = base.merge(df, on="video_id", how="left", suffixes=("", "_norm"))
    if "views_metric_epoch_norm" in merged.columns:
        merged["views_metric_epoch"] = merged["views_metric_epoch"].fillna(
            merged["views_metric_epoch_norm"]
        )
        merged = merged.drop(columns=["views_metric_epoch_norm"])
    write_csv(paths["normalized"] / "videos_normalized.csv", merged.to_dict(orient="records"))
    write_jsonl(paths["normalized"] / "videos_normalized.jsonl", merged.to_dict(orient="records"))

    # Separate PRE-epoch descriptive export (not mixed into opportunity)
    if "views_metric_epoch" in merged.columns:
        pre = merged[merged["views_metric_epoch"] == "PRE_2025_03_31"]
        write_csv(paths["normalized"] / "shorts_pre_epoch.csv", pre.to_dict(orient="records"))
        post = merged[merged["views_metric_epoch"] == "POST_2025_03_31"]
        write_csv(paths["normalized"] / "shorts_post_epoch.csv", post.to_dict(orient="records"))

    _ = get_collection_config  # config touch for methodology linkage
    return merged
