from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from cartoon_factory.budget import BudgetExceeded, BudgetGuard, BudgetPolicy
from cartoon_factory.domain.models import Episode, EpisodeScript, RadarCandidate, SceneScript
from cartoon_factory.domain.states import EpisodeState
from cartoon_factory.pipeline.core import FactoryPipeline
from cartoon_factory.providers.fakes import (
    FakeImageProvider,
    FakeObjectStore,
    FakeTextProvider,
    FakeVideoProvider,
    FakeVoiceProvider,
)


def make_pipeline(policy: BudgetPolicy | None = None) -> FactoryPipeline:
    return FactoryPipeline(
        text=FakeTextProvider(),
        image=FakeImageProvider(),
        video=FakeVideoProvider(),
        voice=FakeVoiceProvider(),
        store=FakeObjectStore(),
        budget=BudgetGuard(policy),
    )


def test_state_machine_rejects_invalid_jump() -> None:
    episode = Episode()
    with pytest.raises(ValueError):
        episode.transition(EpisodeState.RENDERING)


def test_synthetic_radar_candidate_is_rejected() -> None:
    candidate = RadarCandidate(
        radar_run_id="sample",
        generated_at=datetime.now(timezone.utc),
        niche_key="9-12|comedy|short|en|animal",
        opportunity_score=88,
        confidence=0.9,
        evidence_status="INFERENCE",
        evidence_gates_passed=True,
        synthetic=True,
    )
    with pytest.raises(ValueError, match="synthetic"):
        candidate.assert_production_safe()


def test_low_confidence_radar_candidate_is_rejected() -> None:
    candidate = RadarCandidate(
        radar_run_id="live-a",
        generated_at=datetime.now(timezone.utc),
        niche_key="9-12|comedy|short|en|animal",
        opportunity_score=70,
        confidence=0.4,
        evidence_status="INFERENCE",
        evidence_gates_passed=True,
    )
    with pytest.raises(ValueError, match="confidence"):
        candidate.assert_production_safe(min_confidence=0.65)


def test_script_requires_contiguous_scene_indices() -> None:
    with pytest.raises(ValidationError):
        EpisodeScript(
            title="x",
            logline="x",
            hook="x",
            audience="9-12",
            target_duration_seconds=10,
            scenes=[
                SceneScript(
                    index=2,
                    duration_seconds=10,
                    location="room",
                    action="move",
                    camera="wide",
                    emotion="curious",
                    video_prompt="simple animation",
                )
            ],
        )


def test_budget_guard_pauses_before_paid_call() -> None:
    episode = Episode(state=EpisodeState.RENDER_QUEUED, spent_cost_usd=0.8)
    guard = BudgetGuard(BudgetPolicy(episode_soft_cap_usd=0.5, episode_hard_cap_usd=1.0))
    with pytest.raises(BudgetExceeded):
        guard.reserve(
            episode,
            provider="video",
            operation="video",
            estimated_usd=0.3,
            scene_index=1,
        )
    assert episode.state == EpisodeState.PAUSED_BUDGET


def test_fake_pipeline_reaches_final_human_gate() -> None:
    pipeline = make_pipeline()
    episode = Episode()

    pipeline.build_preproduction(episode, "make a 10 second comedy short")
    assert episode.state == EpisodeState.AWAITING_PRODUCTION_APPROVAL
    assert episode.script is not None
    assert len([a for a in pipeline.assets if a.kind == "storyboard"]) == 2
    assert episode.estimated_cost_usd > episode.spent_cost_usd

    pipeline.approve_production(episode)
    pipeline.render(episode)
    assert episode.state == EpisodeState.ASSEMBLING

    pipeline.assemble_manifest(episode)
    pipeline.run_qc(episode)
    assert episode.state == EpisodeState.AWAITING_FINAL_APPROVAL
    assert pipeline.qc_results[-1].passed is True

    pipeline.approve_final(episode)
    assert episode.state == EpisodeState.READY
    assert episode.spent_cost_usd <= 6.0


def test_qc_attributes_missing_scene() -> None:
    pipeline = make_pipeline()
    episode = Episode()
    pipeline.build_preproduction(episode, "test")
    pipeline.approve_production(episode)
    pipeline.render(episode)
    pipeline.assets = [
        asset
        for asset in pipeline.assets
        if not (asset.kind == "video" and asset.scene_index == 2)
    ]
    pipeline.assemble_manifest(episode)
    pipeline.run_qc(episode)

    assert episode.state == EpisodeState.FAILED
    failures = [result for result in pipeline.qc_results if not result.passed]
    assert failures[0].scene_index == 2
