from __future__ import annotations

import re
from datetime import datetime, timezone


ISO8601_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def parse_iso8601_duration(value: str | None) -> int | None:
    if not value:
        return None
    m = ISO8601_DURATION.match(value)
    if not m:
        return None
    days = int(m.group("days") or 0)
    hours = int(m.group("hours") or 0)
    minutes = int(m.group("minutes") or 0)
    seconds = int(m.group("seconds") or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def age_days(publish_date: datetime | None, now: datetime | None = None) -> float | None:
    if publish_date is None:
        return None
    now = now or utcnow()
    if publish_date.tzinfo is None:
        publish_date = publish_date.replace(tzinfo=timezone.utc)
    delta = (now - publish_date).total_seconds() / 86400.0
    return max(delta, 1 / 24)  # floor: 1 hour


def safe_div(num: float | int | None, den: float | int | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return float(num) / float(den)


def normalize_title(title: str | None) -> str:
    if not title:
        return ""
    t = title.lower().strip()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t


def channel_size_bucket(subs: int | None) -> str:
    if subs is None:
        return "unknown"
    if subs < 10_000:
        return "micro"
    if subs < 100_000:
        return "small"
    if subs < 1_000_000:
        return "mid"
    return "mega"
