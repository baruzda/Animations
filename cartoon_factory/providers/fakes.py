from __future__ import annotations

from pathlib import Path

from cartoon_factory.domain.models import EpisodeScript, SceneScript
from cartoon_factory.providers.base import ProviderOutput


class FakeTextProvider:
    name = "fake-text"

    def create_script(self, prompt: str) -> EpisodeScript:
        return EpisodeScript(
            title="Factory smoke episode",
            logline="A tiny character discovers the wrong door.",
            hook="The story opens on the consequence before revealing the cause.",
            audience="9-12",
            target_duration_seconds=10,
            characters=["miko"],
            scenes=[
                SceneScript(
                    index=1,
                    duration_seconds=5,
                    location="hallway",
                    character_ids=["miko"],
                    action="Miko runs away from an open door and looks back.",
                    camera="medium tracking shot",
                    emotion="panic",
                    dialogue="That was the wrong door!",
                    video_prompt="limited animation, clean 2D character, hallway, fast readable action",
                    negative_prompt="extra limbs, text, logo",
                    sfx=["footsteps", "door slam"],
                ),
                SceneScript(
                    index=2,
                    duration_seconds=5,
                    location="hallway",
                    character_ids=["miko"],
                    action="Miko cautiously returns and reaches for the handle.",
                    camera="medium close-up",
                    emotion="curiosity",
                    dialogue=None,
                    video_prompt="limited animation, clean 2D character, cautious reach toward door handle",
                    negative_prompt="extra limbs, text, logo",
                    sfx=["room tone"],
                ),
            ],
        )


class FakeImageProvider:
    name = "fake-image"

    def create_keyframe(self, scene: SceneScript) -> ProviderOutput:
        return ProviderOutput(
            provider=self.name,
            model="fake-keyframe-v1",
            payload=f"PNG:scene:{scene.index}".encode(),
            media_type="image/png",
            estimated_cost_usd=0.02,
            actual_cost_usd=0.02,
            provider_job_id=f"fake-img-{scene.index}",
        )


class FakeVideoProvider:
    name = "fake-video"

    def create_video(self, scene: SceneScript, keyframe: ProviderOutput) -> ProviderOutput:
        return ProviderOutput(
            provider=self.name,
            model="fake-video-v1",
            payload=f"MP4:scene:{scene.index}:{scene.duration_seconds}".encode(),
            media_type="video/mp4",
            estimated_cost_usd=0.05 * scene.duration_seconds,
            actual_cost_usd=0.05 * scene.duration_seconds,
            provider_job_id=f"fake-video-{scene.index}",
        )


class FakeVoiceProvider:
    name = "fake-voice"

    def create_voice(self, text: str, voice_id: str) -> ProviderOutput:
        return ProviderOutput(
            provider=self.name,
            model="fake-voice-v1",
            payload=f"WAV:{voice_id}:{text}".encode(),
            media_type="audio/wav",
            estimated_cost_usd=0.0,
            actual_cost_usd=0.0,
        )


class FakeObjectStore:
    name = "fake-object-store"

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, payload: bytes, media_type: str) -> str:
        del media_type
        self.objects[key] = payload
        return f"memory://{key}"


class LocalObjectStore:
    name = "local-object-store"

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, payload: bytes, media_type: str) -> str:
        del media_type
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path.resolve().as_uri()
