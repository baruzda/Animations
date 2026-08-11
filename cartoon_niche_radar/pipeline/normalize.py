from __future__ import annotations

from typing import Iterable, List, Optional

import pandas as pd

from cartoon_niche_radar.models.schemas import ChannelSizeBucket, NormalizedMetrics, VideoRecord
from cartoon_niche_radar.storage.export import write_csv, write_jsonl
from cartoon_niche_radar.utils.config import get_collection_config, get_scoring_config, project_paths
from cartoon_niche_radar.utils.epochs import ViewsMetricEpoch
from cartoon_niche_radar.utils.shorts import YouTubeContentType
from cartoon_niche_radar.utils.time import age_days, channel_size_bucket, safe_div


def _shorts_opportunity_eligible(rec: VideoRecord) -> bool:
    cfg = get_collection_config().get("shorts_views_metric_break", {})
    required = set(cfg.get("require_content_types_for_opportunity") or ["SHORTS_CONFIRMED"])
    ctype = rec.youtube_content_type
    conf = float(rec.youtube_content_type_confidence or 0)
    if ctype in required:
        return True
    if cfg.get("optional_high_confidence_inferred") and ctype == YouTubeContentType.SHORTS_RULE_INFERRED.value:
        return conf >= float(cfg.get("min_inferred_confidence", 0.7))
    return False


def normalize_record(rec: VideoRecord) -> NormalizedMetrics:
    days = age_days(rec.publish_date)
    views = rec.views
    likes = rec.likes
    comments = rec.comments
    subs = rec.channel_subscribers

    epoch_value = rec.views_metric_epoch or ViewsMetricEpoch.UNKNOWN.value
    shorts_ok = _shorts_opportunity_eligible(rec)
    primary_epoch = (
        get_scoring_config()
        .get("normalization", {})
        .get("shorts_opportunity_epoch", ViewsMetricEpoch.POST_2025_03_31.value)
    )
    # Opportunity: confirmed/high-conf Shorts on POST epoch only.
    # SHORTFORM_PROXY never opportunity-eligible for Shorts view semantics.
    opportunity_eligible = (
        shorts_ok
        and epoch_value == primary_epoch
        and rec.youtube_content_type != YouTubeContentType.SHORTFORM_PROXY.value
    )

    views_per_day = safe_div(views, days)
    views_per_sub = safe_div(views, subs)
    engagement = safe_div((likes or 0) + (comments or 0), views)
    like_rate = safe_div(likes, views)
    comment_rate = safe_div(comments, views)

    viral = None
    if opportunity_eligible and engagement is not None and views_per_day is not None:
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
        youtube_content_type=rec.youtube_content_type,
        sample_role=rec.sample_role or "CORE",
        opportunity_eligible=opportunity_eligible,
        shorts_opportunity_eligible=shorts_ok,
    )


def normalize_many(records: Iterable[VideoRecord]) -> pd.DataFrame:
    return pd.DataFrame([normalize_record(r).model_dump(mode="json") for r in records])


def run_normalize(records: Optional[List[VideoRecord]] = None) -> pd.DataFrame:
    paths = project_paths()
    if records is None:
        raw = paths["raw"] / "youtube_videos.jsonl"
        if not raw.exists():
            raise FileNotFoundError(f"Missing {raw}; run collect first.")
        import orjson

        records = [VideoRecord.model_validate(orjson.loads(line)) for line in raw.open("rb")]

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
                "duration_bin": r.duration_bin,
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
                "youtube_content_type": r.youtube_content_type,
                "youtube_content_type_confidence": r.youtube_content_type_confidence,
                "sample_role": r.sample_role,
                "source_seed_family": r.source_seed_family,
            }
            for r in records
        ]
    )
    merged = base.merge(df, on="video_id", how="left", suffixes=("", "_norm"))
    for col in ("views_metric_epoch", "youtube_content_type", "sample_role"):
        norm_col = f"{col}_norm"
        if norm_col in merged.columns:
            merged[col] = merged[col].fillna(merged[norm_col])
            merged = merged.drop(columns=[norm_col])

    write_csv(paths["normalized"] / "videos_normalized.csv", merged.to_dict(orient="records"))
    write_jsonl(paths["normalized"] / "videos_normalized.jsonl", merged.to_dict(orient="records"))

    if "views_metric_epoch" in merged.columns:
        write_csv(
            paths["normalized"] / "shorts_pre_epoch.csv",
            merged[merged["views_metric_epoch"] == "PRE_2025_03_31"].to_dict(orient="records"),
        )
        write_csv(
            paths["normalized"] / "shorts_post_epoch.csv",
            merged[merged["views_metric_epoch"] == "POST_2025_03_31"].to_dict(orient="records"),
        )
    if "youtube_content_type" in merged.columns:
        write_csv(
            paths["normalized"] / "shortform_proxy.csv",
            merged[merged["youtube_content_type"] == "SHORTFORM_PROXY"].to_dict(orient="records"),
        )
        write_csv(
            paths["normalized"] / "shorts_confirmed.csv",
            merged[merged["youtube_content_type"] == "SHORTS_CONFIRMED"].to_dict(orient="records"),
        )
    return merged
