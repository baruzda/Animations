from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

# FACT: YouTube changed Shorts view counting on 2025-03-31.
SHORTS_VIEWS_BREAK_DATE = date(2025, 3, 31)


class ViewsMetricEpoch(str, Enum):
    PRE_2025_03_31 = "PRE_2025_03_31"
    POST_2025_03_31 = "POST_2025_03_31"
    NON_SHORT = "NON_SHORT"
    UNKNOWN = "UNKNOWN"


def classify_views_metric_epoch(
    *,
    publish_date: Optional[datetime],
    short_or_long: Optional[str],
    break_date: date = SHORTS_VIEWS_BREAK_DATE,
) -> ViewsMetricEpoch:
    if short_or_long is None:
        return ViewsMetricEpoch.UNKNOWN
    value = short_or_long.value if hasattr(short_or_long, "value") else str(short_or_long)
    if value == "long":
        return ViewsMetricEpoch.NON_SHORT
    if value == "unknown":
        return ViewsMetricEpoch.UNKNOWN
    # short
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
