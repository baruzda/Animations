from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Tuple

# FACT: YouTube expanded Shorts max length to 3 minutes around 2024-10-15.
SHORTS_3MIN_EXPANSION_DATE = date(2024, 10, 15)
# FACT: Shorts view counting methodology changed on 2025-03-31.
SHORTS_VIEWS_BREAK_DATE = date(2025, 3, 31)


class YouTubeContentType(str, Enum):
    SHORTS_CONFIRMED = "SHORTS_CONFIRMED"
    SHORTS_RULE_INFERRED = "SHORTS_RULE_INFERRED"
    SHORTFORM_PROXY = "SHORTFORM_PROXY"
    NON_SHORT = "NON_SHORT"
    UNKNOWN = "UNKNOWN"


class DurationBin(str, Enum):
    UNDER_15 = "under_15"
    D15_30 = "15_30"
    D30_45 = "30_45"
    D45_60 = "45_60"
    D60_90 = "60_90"
    D90_180 = "90_180"
    OVER_180 = "over_180"
    UNKNOWN = "unknown"


def duration_bin(duration_seconds: Optional[int]) -> DurationBin:
    if duration_seconds is None:
        return DurationBin.UNKNOWN
    d = int(duration_seconds)
    if d < 15:
        return DurationBin.UNDER_15
    if d <= 30:
        return DurationBin.D15_30
    if d < 45:
        return DurationBin.D30_45
    if d <= 60:
        return DurationBin.D45_60
    if d <= 90:
        return DurationBin.D60_90
    if d <= 180:
        return DurationBin.D90_180
    return DurationBin.OVER_180


def _as_date(publish_date: Optional[datetime]) -> Optional[date]:
    if publish_date is None:
        return None
    if publish_date.tzinfo is not None:
        return publish_date.astimezone(timezone.utc).date()
    return publish_date.date()


def era_shorts_max_seconds(publish_date: Optional[datetime]) -> int:
    """Max Shorts length by publication era (INFERENCE rule, documented)."""
    pd = _as_date(publish_date)
    if pd is None:
        # Conservative unknown-date rule: allow up to 180s for inference attempts
        return 180
    if pd < SHORTS_3MIN_EXPANSION_DATE:
        return 60
    return 180


def classify_youtube_content_type(
    *,
    duration_seconds: Optional[int],
    publish_date: Optional[datetime] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    is_shorts_tab_member: Optional[bool] = None,
    url_path_hint: Optional[str] = None,
    search_video_duration_filter: Optional[str] = None,
) -> Tuple[YouTubeContentType, float, str, list]:
    """Classify YouTube content type with explicit confidence + evidence.

    FACT constraints:
    - search.list videoDuration=short means <4 minutes, NOT confirmed Shorts.
    - Duration alone does not prove Shorts.
    """
    features: list = []
    if duration_seconds is not None:
        features.append(f"duration_seconds={duration_seconds}")
        features.append(f"duration_bin={duration_bin(duration_seconds).value}")

    # Confirmed membership signals
    if is_shorts_tab_member is True:
        features.append("shorts_tab_member=true")
        return YouTubeContentType.SHORTS_CONFIRMED, 0.95, "shorts_tab_membership", features
    if url_path_hint and "/shorts/" in url_path_hint.lower():
        features.append("url_path_contains_shorts")
        return YouTubeContentType.SHORTS_CONFIRMED, 0.9, "url_shorts_path", features

    if duration_seconds is not None and duration_seconds > 180:
        features.append("duration_gt_180")
        return YouTubeContentType.NON_SHORT, 0.9, "duration_over_180", features

    aspect_vertical_or_square = None
    if width and height and width > 0 and height > 0:
        ratio = width / height
        features.append(f"aspect={ratio:.3f}")
        aspect_vertical_or_square = ratio <= 1.05
        features.append(f"vertical_or_square={aspect_vertical_or_square}")

    max_sec = era_shorts_max_seconds(publish_date)
    features.append(f"era_max_seconds={max_sec}")
    pd = _as_date(publish_date)
    if pd is not None:
        features.append(f"publish_date={pd.isoformat()}")
        features.append(
            "era="
            + (
                "pre_2024_10_15"
                if pd < SHORTS_3MIN_EXPANSION_DATE
                else "post_2024_10_15"
            )
        )

    if (
        duration_seconds is not None
        and duration_seconds <= max_sec
        and aspect_vertical_or_square is True
    ):
        conf = 0.75 if duration_seconds <= 60 else 0.7
        return (
            YouTubeContentType.SHORTS_RULE_INFERRED,
            conf,
            "duration_within_era_max_and_vertical_square",
            features,
        )

    # search.list videoDuration=short is only a short-form proxy, never confirmation
    if search_video_duration_filter == "short":
        features.append("search_filter=videoDuration.short")
        if duration_seconds is not None and duration_seconds <= 180:
            return (
                YouTubeContentType.SHORTFORM_PROXY,
                0.55,
                "search_videoDuration_short_proxy",
                features,
            )
        return YouTubeContentType.SHORTFORM_PROXY, 0.4, "search_videoDuration_short_proxy", features

    if duration_seconds is not None and duration_seconds <= 180:
        # Duration-only short-form without orientation/membership evidence
        return (
            YouTubeContentType.SHORTFORM_PROXY,
            0.45,
            "duration_only_shortform_proxy",
            features,
        )

    if duration_seconds is None and aspect_vertical_or_square is None:
        return YouTubeContentType.UNKNOWN, 0.0, "insufficient_evidence", features

    return YouTubeContentType.UNKNOWN, 0.2, "ambiguous_signals", features


def content_type_as_dict(
    content_type: YouTubeContentType,
    confidence: float,
    source: str,
    features: list,
) -> Dict[str, Any]:
    return {
        "value": content_type.value,
        "confidence": confidence,
        "source": source,
        "evidence_features": features,
        "kind": "INFERENCE" if content_type != YouTubeContentType.UNKNOWN else "UNKNOWN",
    }
