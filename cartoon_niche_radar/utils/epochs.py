from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from cartoon_niche_radar.utils.shorts import (
    SHORTS_VIEWS_BREAK_DATE,
    YouTubeContentType,
)

# Re-export break date for callers
SHORTS_VIEWS_BREAK_DATE = SHORTS_VIEWS_BREAK_DATE


class ViewsMetricEpoch(str, Enum):
    PRE_2025_03_31 = "PRE_2025_03_31"
    POST_2025_03_31 = "POST_2025_03_31"
    NON_SHORT = "NON_SHORT"
    SHORTFORM_PROXY = "SHORTFORM_PROXY"
    UNKNOWN = "UNKNOWN"


def classify_views_metric_epoch(
    *,
    publish_date: Optional[datetime],
    youtube_content_type: Optional[str],
    content_type_confidence: float = 0.0,
    min_inferred_confidence: float = 0.7,
    break_date: date = SHORTS_VIEWS_BREAK_DATE,
) -> ViewsMetricEpoch:
    """Apply Shorts view-count epoch only to confirmed / high-confidence inferred Shorts.

    FACT: POST/PRE_2025_03_31 semantics apply to Shorts view counting.
    SHORTFORM_PROXY must NOT receive Shorts opportunity epoch treatment.
    """
    ctype = youtube_content_type
    if hasattr(ctype, "value"):
        ctype = ctype.value  # type: ignore[union-attr]
    ctype = str(ctype or "UNKNOWN")

    if ctype == YouTubeContentType.NON_SHORT.value:
        return ViewsMetricEpoch.NON_SHORT
    if ctype == YouTubeContentType.SHORTFORM_PROXY.value:
        return ViewsMetricEpoch.SHORTFORM_PROXY
    if ctype == YouTubeContentType.UNKNOWN.value:
        return ViewsMetricEpoch.UNKNOWN

    eligible = ctype == YouTubeContentType.SHORTS_CONFIRMED.value or (
        ctype == YouTubeContentType.SHORTS_RULE_INFERRED.value
        and content_type_confidence >= min_inferred_confidence
    )
    if not eligible:
        # Low-confidence inferred Shorts → treat as unknown for opportunity epoch
        return ViewsMetricEpoch.UNKNOWN

    if publish_date is None:
        return ViewsMetricEpoch.UNKNOWN
    pd = publish_date
    if pd.tzinfo is not None:
        pd_date = pd.astimezone(timezone.utc).date()
    else:
        pd_date = pd.date()
    if pd_date < break_date:
        return ViewsMetricEpoch.PRE_2025_03_31
    return ViewsMetricEpoch.POST_2025_03_31


# Backward-compatible wrapper used by older call sites (short_or_long heuristic).
def classify_views_metric_epoch_legacy(
    *,
    publish_date: Optional[datetime],
    short_or_long: Optional[str],
    break_date: date = SHORTS_VIEWS_BREAK_DATE,
) -> ViewsMetricEpoch:
    value = short_or_long.value if hasattr(short_or_long, "value") else str(short_or_long or "unknown")
    if value == "long":
        return classify_views_metric_epoch(
            publish_date=publish_date,
            youtube_content_type=YouTubeContentType.NON_SHORT.value,
        )
    # Do NOT treat legacy "short" as confirmed Shorts
    return classify_views_metric_epoch(
        publish_date=publish_date,
        youtube_content_type=YouTubeContentType.SHORTFORM_PROXY.value,
    )
