from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from cartoon_niche_radar.collectors.quota import QuotaExceededError, QuotaManager
from cartoon_niche_radar.collectors.resume_state import CollectionState
from cartoon_niche_radar.models.evidence import Evidenced, EvidenceKind
from cartoon_niche_radar.models.schemas import MadeForKids, ShortOrLong, VideoRecord
from cartoon_niche_radar.pipeline.classify import HeuristicClassifier
from cartoon_niche_radar.pipeline.normalize import normalize_record
from cartoon_niche_radar.utils.config import clear_config_caches, load_yaml
from cartoon_niche_radar.utils.epochs import ViewsMetricEpoch, classify_views_metric_epoch
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
        views_metric_epoch="PRE_2025_03_31",
    )
    m = normalize_record(rec)
    assert m.views_metric_epoch == "PRE_2025_03_31"
    assert m.opportunity_eligible is False
    assert m.viral_coefficient is None


def test_shorts_epoch_classifier() -> None:
    pre = classify_views_metric_epoch(
        publish_date=datetime(2025, 3, 30, tzinfo=timezone.utc),
        short_or_long="short",
    )
    post = classify_views_metric_epoch(
        publish_date=datetime(2025, 3, 31, tzinfo=timezone.utc),
        short_or_long="short",
    )
    long = classify_views_metric_epoch(
        publish_date=datetime(2025, 6, 1, tzinfo=timezone.utc),
        short_or_long="long",
    )
    assert pre == ViewsMetricEpoch.PRE_2025_03_31
    assert post == ViewsMetricEpoch.POST_2025_03_31
    assert long == ViewsMetricEpoch.NON_SHORT


def test_classifier_unknown_on_empty() -> None:
    clf = HeuristicClassifier(min_confidence=0.55)
    rec = VideoRecord(video_id="x", channel_id="c", title="aaaa", description="")
    result = clf.classify(rec)
    assert result.theme.kind == EvidenceKind.UNKNOWN
    assert result.target_age.kind == EvidenceKind.UNKNOWN
    assert result.classifier_version


def test_classifier_does_not_use_made_for_kids_as_age() -> None:
    clf = HeuristicClassifier(min_confidence=0.55)
    rec = VideoRecord(
        video_id="x",
        channel_id="c",
        title="random clip xyz",
        description="no age cues here",
        made_for_kids=MadeForKids.TRUE,
        duration_seconds=20,
    )
    result = clf.classify(rec)
    assert result.made_for_kids_fact == "true"
    assert result.target_age.kind == EvidenceKind.UNKNOWN


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


def test_quota_manager_stops_before_exceed(tmp_path: Path) -> None:
    clear_config_caches()
    cfg = load_yaml("quota.yaml")
    cfg = dict(cfg)
    cfg["logging"] = {"enabled": True, "path": str(tmp_path / "quota.jsonl")}
    cfg["buckets"] = {
        "SEARCH": {"endpoints": {"search.list": {"cost": 1}}, "daily_limit": 2},
        "BATCH_STATS": {
            "endpoints": {"videos.batchGetStats": {"cost": 1}},
            "daily_limit": 10,
        },
        "GENERAL": {
            "endpoints": {"videos.list": {"cost": 1}},
            "daily_limit": 10,
            "default_endpoint_cost": 1,
        },
    }
    qm = QuotaManager(cfg)
    qm.charge("search.list", {"q": "a"}, success=True)
    qm.charge("search.list", {"q": "b"}, success=True)
    assert qm.remaining("SEARCH") == 0
    try:
        qm.check_or_raise("search.list")
        raised = False
    except QuotaExceededError:
        raised = True
    assert raised


def test_resume_state_idempotent(tmp_path: Path) -> None:
    state = CollectionState(path=tmp_path / "state.json")
    assert state.add_discovered(["a", "b"]) == 2
    assert state.add_discovered(["a", "c"]) == 1
    state.mark_query_done("q1")
    state.save()
    state2 = CollectionState(path=tmp_path / "state.json")
    assert state2.is_query_done("q1")
    assert state2.discovered() == {"a", "b", "c"}
    assert state2.pending_enrichment() == ["a", "b", "c"]
    state2.add_enriched(["a"])
    assert state2.pending_enrichment() == ["b", "c"]
