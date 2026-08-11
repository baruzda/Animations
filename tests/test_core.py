from __future__ import annotations

from datetime import datetime, timezone

from cartoon_niche_radar.models.evidence import Evidenced, EvidenceKind
from cartoon_niche_radar.models.schemas import ShortOrLong, VideoRecord
from cartoon_niche_radar.pipeline.classify import HeuristicClassifier
from cartoon_niche_radar.pipeline.normalize import normalize_record
from cartoon_niche_radar.utils.time import parse_iso8601_duration


def test_parse_duration() -> None:
    assert parse_iso8601_duration("PT45S") == 45
    assert parse_iso8601_duration("PT1M30S") == 90
    assert parse_iso8601_duration(None) is None


def test_evidenced_unknown() -> None:
    e = Evidenced.unknown("no data")
    assert e.kind == EvidenceKind.UNKNOWN
    assert e.value is None


def test_normalize_views_per_day() -> None:
    rec = VideoRecord(
        video_id="x",
        channel_id="c",
        views=1000,
        likes=50,
        comments=10,
        channel_subscribers=1000,
        publish_date=datetime.now(timezone.utc),
        short_or_long=ShortOrLong.SHORT,
        youtube_content_type="SHORTS_CONFIRMED",
        youtube_content_type_confidence=0.95,
        views_metric_epoch="POST_2025_03_31",
    )
    m = normalize_record(rec)
    assert m.views_per_day is not None
    assert m.engagement_rate is not None
    assert m.opportunity_eligible is True


def test_pre_epoch_not_opportunity_eligible_for_viral() -> None:
    rec = VideoRecord(
        video_id="pre",
        channel_id="c",
        views=10000,
        likes=100,
        comments=10,
        channel_subscribers=1000,
        publish_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        short_or_long=ShortOrLong.SHORT,
        youtube_content_type="SHORTS_CONFIRMED",
        youtube_content_type_confidence=0.95,
        views_metric_epoch="PRE_2025_03_31",
    )
    m = normalize_record(rec)
    assert m.views_metric_epoch == "PRE_2025_03_31"
    assert m.opportunity_eligible is False
    assert m.viral_coefficient is None


def test_classifier_unknown_on_empty() -> None:
    clf = HeuristicClassifier(min_confidence=0.55)
    rec = VideoRecord(video_id="x", channel_id="c", title="aaaa", description="")
    result = clf.classify(rec)
    assert result.theme.kind == EvidenceKind.UNKNOWN
    assert result.target_age.kind == EvidenceKind.UNKNOWN
    assert result.classifier_version


def test_classifier_theme_hit() -> None:
    clf = HeuristicClassifier(min_confidence=0.55)
    rec = VideoRecord(
        video_id="x",
        channel_id="c",
        title="school funny relatable cartoon short",
        description="teenager high school teen cartoon",
        duration_seconds=28,
    )
    result = clf.classify(rec)
    assert result.format.value == "short_15_30"
    assert result.format.kind == EvidenceKind.INFERENCE
