from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from cartoon_factory.domain.models import EpisodeScript, SceneScript


@dataclass(frozen=True)
class ProviderOutput:
    provider: str
    model: str
    payload: bytes
    media_type: str
    estimated_cost_usd: float = 0.0
    actual_cost_usd: float = 0.0
    provider_job_id: str = ""


class TextProvider(Protocol):
    name: str

    def create_script(self, prompt: str) -> EpisodeScript:
        ...


class ImageProvider(Protocol):
    name: str

    def create_keyframe(self, scene: SceneScript) -> ProviderOutput:
        ...


class VideoProvider(Protocol):
    name: str

    def create_video(self, scene: SceneScript, keyframe: ProviderOutput) -> ProviderOutput:
        ...


class VoiceProvider(Protocol):
    name: str

    def create_voice(self, text: str, voice_id: str) -> ProviderOutput:
        ...


class SoundProvider(Protocol):
    name: str

    def create_sound(self, prompt: str, duration_seconds: float) -> ProviderOutput:
        ...


class ObjectStore(Protocol):
    name: str

    def put(self, key: str, payload: bytes, media_type: str) -> str:
        ...
