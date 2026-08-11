from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from cartoon_niche_radar.collectors.query_scheduler import QueryScheduler
from cartoon_niche_radar.collectors.quota import QuotaManager
from cartoon_niche_radar.collectors.resume_state import CollectionState
from cartoon_niche_radar.collectors.youtube import YouTubeCollector
from cartoon_niche_radar.models.evidence import EvidenceKind
from cartoon_niche_radar.models.schemas import MadeForKids, ShortOrLong, VideoRecord
from cartoon_niche_radar.pipeline.classify import HeuristicClassifier, OpenAIClassifier
from cartoon_niche_radar.pipeline.normalize import normalize_record
from cartoon_niche_radar.utils.config import clear_config_caches, get_collection_config, load_yaml
from cartoon_niche_radar.utils.epochs import ViewsMetricEpoch, classify_views_metric_epoch
from cartoon_niche_radar.utils.shorts import (
    YouTubeContentType,
    classify_youtube_content_type,
    duration_bin,
)


def test_fresh_discovery_caps_do_not_collapse_after_first_item(tmp_path: Path) -> None:
    state = CollectionState(path=tmp_path / "state.json")
    collector = YouTubeCollector(api_key=None, state=state, require_api_key=False)
    seed = {
        "theme": "school",
        "seed_id": "CORE|q|school",
        "target_age_hypothesis": "UNKNOWN",
        "sample_role": "CORE",
    }
    assert collector._within_strata_caps(seed) is True
    assert state.accept_discovered("v1", theme="school", seed_id=seed["seed_id"], sample_role="CORE")
    # After first item, denominator is 1 but share checks use > max_share; still allow other themes
    seed2 = {
        "theme": "gaming",
        "seed_id": "CORE|q|gaming",
        "target_age_hypothesis": "UNKNOWN",
        "sample_role": "CORE",
    }
    assert collector._within_strata_caps(seed2) is True
    # Same theme at 100% share should block further same-theme accepts when max_share_per_theme < 1
    assert collector._within_strata_caps(seed) is False


def test_caps_use_current_run_ids(tmp_path: Path) -> None:
    state = CollectionState(path=tmp_path / "state.json")
    collector = YouTubeCollector(api_key=None, state=state, require_api_key=False)
    seed = {
        "theme": "animals",
        "seed_id": "CORE|q|animals",
        "target_age_hypothesis": "UNKNOWN",
        "sample_role": "CORE",
    }
    # Simulate immediate persist of run IDs (denominator grows with accepts)
    for i in range(10):
        state.accept_discovered(
            f"v{i}",
            theme="animals" if i < 2 else "music",
            seed_id=f"seed{i}",
            sample_role="CORE",
        )
    assert state.effective_discovered_count() == 10
    # animals share = 2/10 = 0.2 > default 0.12 → blocked
    assert collector._within_strata_caps(seed) is False


def test_discovered_ids_persist_before_page_progress(tmp_path: Path) -> None:
    state = CollectionState(path=tmp_path / "state.json")
    collector = YouTubeCollector(api_key=None, state=state, require_api_key=False)
    seed = {
        "theme": "fantasy",
        "seed_id": "CORE|q|fantasy",
        "target_age_hypothesis": "UNKNOWN",
        "sample_role": "CORE",
        "source_seed_family": "core:fantasy",
    }
    ok = collector._accept_id("abc123", seed=seed, channel_id="ch1")
    assert ok is True
    # Reload from disk — ID must already be persisted before any page token write
    state2 = CollectionState(path=tmp_path / "state.json")
    assert "abc123" in state2.discovered()
    assert state2.data["video_meta"]["abc123"]["sample_role"] == "CORE"


def test_resume_after_mid_discovery_crash_preserves_ids(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    state = CollectionState(path=path)
    collector = YouTubeCollector(api_key=None, state=state, require_api_key=False)
    seed = {
        "theme": "mystery",
        "seed_id": "CORE|q|mystery",
        "target_age_hypothesis": "UNKNOWN",
        "sample_role": "CORE",
    }
    collector._accept_id("keep1", seed=seed, channel_id="c")
    collector._accept_id("keep2", seed=seed, channel_id="c")
    state.set_page_token("q1|date|US|en", "PAGE_TOKEN_X")
    state.save()
    # Crash simulation: new process
    resumed = CollectionState(path=path)
    assert resumed.discovered() == {"keep1", "keep2"}
    assert resumed.get_page_token("q1|date|US|en") == "PAGE_TOKEN_X"


@pytest.mark.parametrize(
    "seconds,expected_bin",
    [
        (45, "45_60"),
        (90, "60_90"),
        (120, "90_180"),
        (180, "90_180"),
        (181, "over_180"),
    ],
)
def test_duration_bins(seconds: int, expected_bin: str) -> None:
    assert duration_bin(seconds).value == expected_bin


def test_shortform_proxy_not_confirmed_shorts() -> None:
    ctype, conf, source, feats = classify_youtube_content_type(
        duration_seconds=45,
        publish_date=datetime(2025, 6, 1, tzinfo=timezone.utc),
        search_video_duration_filter="short",
    )
    assert ctype == YouTubeContentType.SHORTFORM_PROXY
    assert "search_filter=videoDuration.short" in feats
    epoch = classify_views_metric_epoch(
        publish_date=datetime(2025, 6, 1, tzinfo=timezone.utc),
        youtube_content_type=ctype.value,
        content_type_confidence=conf,
    )
    assert epoch == ViewsMetricEpoch.SHORTFORM_PROXY


def test_pre_post_2024_10_15_shorts_rule_inferred() -> None:
    pre = datetime(2024, 10, 14, tzinfo=timezone.utc)
    post = datetime(2024, 10, 16, tzinfo=timezone.utc)
    # 90s vertical before expansion → not inferred Shorts (over era max 60)
    ctype_pre, _, _, _ = classify_youtube_content_type(
        duration_seconds=90, publish_date=pre, width=1080, height=1920
    )
    assert ctype_pre == YouTubeContentType.SHORTFORM_PROXY
    # 90s vertical after expansion → SHORTS_RULE_INFERRED
    ctype_post, conf, _, _ = classify_youtube_content_type(
        duration_seconds=90, publish_date=post, width=1080, height=1920
    )
    assert ctype_post == YouTubeContentType.SHORTS_RULE_INFERRED
    assert conf >= 0.7


def test_181_sec_is_non_short() -> None:
    ctype, _, _, _ = classify_youtube_content_type(duration_seconds=181)
    assert ctype == YouTubeContentType.NON_SHORT


def test_confirmed_shorts_tab_membership() -> None:
    ctype, conf, source, _ = classify_youtube_content_type(
        duration_seconds=120,
        is_shorts_tab_member=True,
    )
    assert ctype == YouTubeContentType.SHORTS_CONFIRMED
    assert source == "shorts_tab_membership"
    assert conf >= 0.9


def test_core_seeds_have_no_numeric_age_labels() -> None:
    clear_config_caches()
    collector = YouTubeCollector(api_key=None, require_api_key=False)
    for seed in collector.build_core_seeds():
        assert seed["sample_role"] == "CORE"
        for banned in ["2-5", "6-8", "9-12", "13-17", "18-24", "2–5", "13–17"]:
            assert banned not in seed["query"]
        assert seed["target_age_hypothesis"] == "UNKNOWN"


def test_coverage_seeds_tagged() -> None:
    clear_config_caches()
    collector = YouTubeCollector(api_key=None, require_api_key=False)
    cov = collector.build_coverage_seeds()
    assert cov
    assert all(s["sample_role"] == "COVERAGE" for s in cov)
    assert all(s.get("source_seed_family") for s in cov)


def test_query_scheduler_includes_viewcount_and_published_after(tmp_path: Path) -> None:
    clear_config_caches()
    collection = get_collection_config()
    quota = load_yaml("quota.yaml")
    sched = QueryScheduler(collection, quota)
    sched.plan_path = tmp_path / "plan.json"
    seeds = [
        {
            "seed_id": "CORE|a|school",
            "query": "cartoon school",
            "theme": "school",
            "sample_role": "CORE",
            "source_seed_family": "core:school",
        },
        {
            "seed_id": "CORE|a|gaming",
            "query": "cartoon gaming",
            "theme": "gaming",
            "sample_role": "CORE",
            "source_seed_family": "core:gaming",
        },
    ]
    plan = sched.build_plan(seeds, pt_quota_date="2026-08-11", max_calls=30)
    orders = {s["order"] for s in plan["slots"]}
    assert "viewCount" in orders
    assert "date" in orders
    assert "relevance" in orders
    assert plan["lookback_days"] == 365
    assert plan["publishedAfter"].endswith("Z")
    assert all(s.get("publishedAfter") for s in plan["slots"])
    assert plan["omitted_dimensions"]["orders_omitted"] == []


def test_search_params_include_published_after(tmp_path: Path) -> None:
    """Verify publishedAfter reaches request kwargs (mocked YouTube client)."""
    clear_config_caches()
    state = CollectionState(path=tmp_path / "state.json")
    collector = YouTubeCollector(api_key="fake", state=state, require_api_key=False)
    collector.api_key = "fake"
    mock_youtube = MagicMock()
    mock_list = MagicMock()
    mock_youtube.search.return_value.list.return_value = mock_list
    mock_list.execute.return_value = {"items": []}
    collector.youtube = mock_youtube
    collector.quota = QuotaManager(
        {
            "timezone": "America/Los_Angeles",
            "buckets": {
                "SEARCH": {"endpoints": {"search.list": {"cost": 1}}, "daily_limit": 10},
                "BATCH_STATS": {"endpoints": {"videos.batchGetStats": {"cost": 1}}, "daily_limit": 10},
                "GENERAL": {"endpoints": {}, "daily_limit": 10, "default_endpoint_cost": 1},
            },
            "logging": {"enabled": False},
        }
    )
    collector._search_page(
        "cartoon",
        order="date",
        region_code="US",
        relevance_language="en",
        page_token=None,
        max_results=10,
        published_after="2025-08-11T00:00:00Z",
    )
    kwargs = mock_youtube.search.return_value.list.call_args.kwargs
    assert kwargs.get("publishedAfter") == "2025-08-11T00:00:00Z"
    assert collector.last_search_params is not None
    assert collector.last_search_params["publishedAfter"] == "2025-08-11T00:00:00Z"


def test_openai_classifier_real_path_and_explicit_fallback() -> None:
    rec = VideoRecord(
        video_id="x",
        channel_id="c",
        title="school cartoon",
        description="teen high school",
        duration_seconds=30,
        made_for_kids=MadeForKids.FALSE,
    )

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("boom")

    clf = OpenAIClassifier(client=FakeClient())
    result = clf.classify(rec)
    assert result.classifier == "FALLBACK_HEURISTIC"

    class OkClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    msg = MagicMock()
                    msg.choices = [
                        MagicMock(
                            message=MagicMock(
                                content=(
                                    '{"target_age":{"value":"13-17","confidence":0.8,'
                                    '"evidence_features":["title:high school"]},'
                                    '"theme":{"value":"school","confidence":0.9,'
                                    '"evidence_features":["title:school"]},'
                                    '"visual_style":{"value":null,"confidence":0},'
                                    '"character_type":{"value":null,"confidence":0},'
                                    '"emotional_trigger":{"value":null,"confidence":0},'
                                    '"dialogue":{"value":null,"confidence":0},'
                                    '"music":{"value":null,"confidence":0},'
                                    '"series_potential":{"value":null,"confidence":0},'
                                    '"hook":{"value":"question_hook","confidence":0.9},'
                                    '"story_structure":{"value":"twist_ending","confidence":0.9},'
                                    '"content_evidence":false}'
                                )
                            )
                        )
                    ]
                    return msg.choices[0] if False else msg  # placeholder

    # Fix OkClient to return proper structure
    class OkClient2:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    choice = MagicMock()
                    choice.message.content = (
                        '{"target_age":{"value":"13-17","confidence":0.8,'
                        '"evidence_features":["title:high school"]},'
                        '"theme":{"value":"school","confidence":0.9,'
                        '"evidence_features":["title:school"]},'
                        '"visual_style":{"value":null,"confidence":0},'
                        '"character_type":{"value":null,"confidence":0},'
                        '"emotional_trigger":{"value":null,"confidence":0},'
                        '"dialogue":{"value":null,"confidence":0},'
                        '"music":{"value":null,"confidence":0},'
                        '"series_potential":{"value":null,"confidence":0},'
                        '"hook":{"value":"question_hook","confidence":0.9},'
                        '"story_structure":{"value":"twist_ending","confidence":0.9},'
                        '"content_evidence":false}'
                    )
                    resp = MagicMock()
                    resp.choices = [choice]
                    return resp

    clf2 = OpenAIClassifier(client=OkClient2())
    result2 = clf2.classify(rec)
    assert result2.classifier == "openai"
    assert result2.theme.value == "school"
    # hook/story without content_evidence => UNKNOWN
    assert result2.hook.kind == EvidenceKind.UNKNOWN
    assert result2.story_structure.kind == EvidenceKind.UNKNOWN


def test_heuristic_does_not_use_mfk_as_age() -> None:
    clf = HeuristicClassifier(min_confidence=0.55)
    rec = VideoRecord(
        video_id="x",
        channel_id="c",
        title="random xyz",
        description="no cues",
        made_for_kids=MadeForKids.TRUE,
        duration_seconds=20,
    )
    result = clf.classify(rec)
    assert result.target_age.kind == EvidenceKind.UNKNOWN
    assert result.made_for_kids_fact == "true"


def test_proxy_not_opportunity_eligible() -> None:
    rec = VideoRecord(
        video_id="p",
        channel_id="c",
        views=1000,
        likes=10,
        comments=1,
        channel_subscribers=1000,
        publish_date=datetime(2025, 6, 1, tzinfo=timezone.utc),
        duration_seconds=45,
        youtube_content_type="SHORTFORM_PROXY",
        youtube_content_type_confidence=0.55,
        views_metric_epoch="SHORTFORM_PROXY",
        short_or_long=ShortOrLong.SHORT,
    )
    m = normalize_record(rec)
    assert m.opportunity_eligible is False
    assert m.viral_coefficient is None
