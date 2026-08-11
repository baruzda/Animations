from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Optional

from cartoon_factory.budget import BudgetGuard
from cartoon_factory.domain.models import Asset, CostEvent, Episode, QCResult
from cartoon_factory.domain.states import EpisodeState
from cartoon_factory.providers.base import (
    ImageProvider,
    ObjectStore,
    ProviderOutput,
    TextProvider,
    VideoProvider,
    VoiceProvider,
)


class FactoryPipeline:
    """Small synchronous V1 orchestrator.

    Persistence/work queues can replace the in-memory collections later without
    changing provider contracts or state transitions.
    """

    def __init__(
        self,
        *,
        text: TextProvider,
        image: ImageProvider,
        video: VideoProvider,
        voice: VoiceProvider,
        store: ObjectStore,
        budget: Optional[BudgetGuard] = None,
    ) -> None:
        self.text = text
        self.image = image
        self.video = video
        self.voice = voice
        self.store = store
        self.budget = budget or BudgetGuard()
        self.assets: List[Asset] = []
        self.cost_events: List[CostEvent] = []
        self.qc_results: List[QCResult] = []
        self.keyframes: Dict[str, ProviderOutput] = {}

    def _paid_call(
        self,
        episode: Episode,
        *,
        provider: str,
        operation: str,
        estimate: float,
        scene_index: Optional[int],
        call,
    ):
        event = self.budget.reserve(
            episode,
            provider=provider,
            operation=operation,
            estimated_usd=estimate,
            scene_index=scene_index,
        )
        self.cost_events.append(event)
        output = call()
        actual = float(getattr(output, "actual_cost_usd", estimate))
        self.budget.reconcile(episode, event, actual)
        return output

    def _persist_output(
        self,
        episode: Episode,
        output: ProviderOutput,
        *,
        kind: str,
        scene_index: Optional[int],
        extension: str,
    ) -> Asset:
        key = f"episodes/{episode.id}/{kind}/scene-{scene_index or 0}.{extension}"
        uri = self.store.put(key, output.payload, output.media_type)
        checksum = hashlib.sha256(output.payload).hexdigest()
        asset = Asset(
            episode_id=episode.id,
            scene_index=scene_index,
            kind=kind,
            provider=output.provider,
            model=output.model,
            storage_uri=uri,
            checksum=checksum,
            provider_job_id=output.provider_job_id or None,
            cost_usd=output.actual_cost_usd,
        )
        self.assets.append(asset)
        return asset

    def build_preproduction(self, episode: Episode, prompt: str) -> Episode:
        episode.transition(EpisodeState.SCRIPTING)
        script_estimate = self.text.estimate_script(prompt)
        script = self._paid_call(
            episode,
            provider=self.text.name,
            operation="script",
            estimate=script_estimate,
            scene_index=None,
            call=lambda: _ScriptOutput(self.text.create_script(prompt), script_estimate),
        ).script
        episode.script = script
        episode.transition(EpisodeState.STORYBOARDING)

        render_estimate = 0.0
        for scene in script.scenes:
            estimate = self.image.estimate_keyframe(scene)
            output = self._paid_call(
                episode,
                provider=self.image.name,
                operation="keyframe",
                estimate=estimate,
                scene_index=scene.index,
                call=lambda scene=scene: self.image.create_keyframe(scene),
            )
            self.keyframes[f"{episode.id}:{scene.index}"] = output
            self._persist_output(
                episode,
                output,
                kind="storyboard",
                scene_index=scene.index,
                extension="png",
            )
            render_estimate += self.video.estimate_video(scene)
            if scene.dialogue:
                render_estimate += self.voice.estimate_voice(scene.dialogue, "default")

        episode.estimated_cost_usd = episode.spent_cost_usd + render_estimate
        episode.transition(EpisodeState.AWAITING_PRODUCTION_APPROVAL)
        return episode

    def approve_production(self, episode: Episode) -> Episode:
        episode.transition(EpisodeState.RENDER_QUEUED)
        return episode

    def render(self, episode: Episode) -> Episode:
        if episode.script is None:
            raise ValueError("episode has no script")
        episode.transition(EpisodeState.RENDERING)
        for scene in episode.script.scenes:
            key = f"{episode.id}:{scene.index}"
            keyframe = self.keyframes.get(key)
            if keyframe is None:
                raise ValueError(f"missing keyframe for scene {scene.index}")

            video_estimate = self.video.estimate_video(scene)
            video = self._paid_call(
                episode,
                provider=self.video.name,
                operation="video",
                estimate=video_estimate,
                scene_index=scene.index,
                call=lambda scene=scene, keyframe=keyframe: self.video.create_video(scene, keyframe),
            )
            self._persist_output(
                episode,
                video,
                kind="video",
                scene_index=scene.index,
                extension="mp4",
            )

            if scene.dialogue:
                voice_estimate = self.voice.estimate_voice(scene.dialogue, "default")
                voice = self._paid_call(
                    episode,
                    provider=self.voice.name,
                    operation="voice",
                    estimate=voice_estimate,
                    scene_index=scene.index,
                    call=lambda text=scene.dialogue: self.voice.create_voice(text or "", "default"),
                )
                self._persist_output(
                    episode,
                    voice,
                    kind="voice",
                    scene_index=scene.index,
                    extension="wav",
                )

        episode.transition(EpisodeState.ASSEMBLING)
        return episode

    def assemble_manifest(self, episode: Episode) -> Episode:
        """Fake-safe assembly boundary.

        Real FFmpeg assembly consumes the same manifest; fake CI never pretends
        its provider bytes are valid media.
        """
        if episode.script is None:
            raise ValueError("episode has no script")
        video_assets = sorted(
            [a for a in self.assets if a.episode_id == episode.id and a.kind == "video"],
            key=lambda a: a.scene_index or 0,
        )
        manifest = {
            "episode_id": episode.id,
            "scene_count": len(episode.script.scenes),
            "videos": [a.model_dump(mode="json") for a in video_assets],
        }
        payload = json.dumps(manifest, sort_keys=True).encode()
        output = ProviderOutput(
            provider="factory",
            model="assembly-manifest-v1",
            payload=payload,
            media_type="application/json",
        )
        self._persist_output(
            episode,
            output,
            kind="manifest",
            scene_index=None,
            extension="json",
        )
        episode.transition(EpisodeState.QC)
        return episode

    def run_qc(self, episode: Episode) -> Episode:
        if episode.script is None:
            raise ValueError("episode has no script")
        expected = {scene.index for scene in episode.script.scenes}
        actual = {
            asset.scene_index
            for asset in self.assets
            if asset.episode_id == episode.id and asset.kind == "video" and asset.scene_index is not None
        }
        missing = sorted(expected - actual)
        if missing:
            for scene_index in missing:
                self.qc_results.append(
                    QCResult(
                        episode_id=episode.id,
                        passed=False,
                        code="MISSING_SCENE_VIDEO",
                        message=f"missing video asset for scene {scene_index}",
                        scene_index=scene_index,
                    )
                )
            episode.transition(EpisodeState.FAILED)
            return episode

        self.qc_results.append(
            QCResult(
                episode_id=episode.id,
                passed=True,
                code="V1_ASSET_COMPLETENESS",
                message="all expected scene video assets exist",
            )
        )
        episode.transition(EpisodeState.AWAITING_FINAL_APPROVAL)
        return episode

    def approve_final(self, episode: Episode) -> Episode:
        episode.transition(EpisodeState.READY)
        return episode


class _ScriptOutput:
    """Adapter so script generation follows the same budget reconciliation path."""

    def __init__(self, script, cost: float) -> None:
        self.script = script
        self.actual_cost_usd = cost
