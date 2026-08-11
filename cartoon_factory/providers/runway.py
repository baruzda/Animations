from __future__ import annotations

import base64
import math
import time
from dataclasses import dataclass

import httpx

from cartoon_factory.domain.models import SceneScript
from cartoon_factory.providers.base import ProviderOutput


class RunwayError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunwayConfig:
    api_secret: str
    model: str = "gen4_turbo"
    ratio: str = "720:1280"
    api_version: str = "2024-11-06"
    base_url: str = "https://api.dev.runwayml.com"
    poll_interval_seconds: float = 2.0
    timeout_seconds: float = 300.0

    def __post_init__(self) -> None:
        if not self.api_secret.strip():
            raise ValueError("Runway API secret is required")
        if self.model != "gen4_turbo":
            raise ValueError("V1 Runway adapter intentionally supports gen4_turbo only")
        if self.ratio != "720:1280":
            raise ValueError("V1 Runway adapter intentionally supports portrait 720:1280 only")


class RunwayVideoProvider:
    """Runway Gen-4 Turbo image-to-video provider.

    The provider returns downloaded bytes rather than ephemeral Runway output URLs,
    so the Factory can immediately persist the asset into owned storage.
    """

    name = "runway"
    cost_per_second_usd = 0.05
    max_inline_image_bytes = 3_500_000

    def __init__(self, config: RunwayConfig, client: httpx.Client | None = None) -> None:
        self.config = config
        self.client = client or httpx.Client(timeout=30.0)

    @staticmethod
    def billed_duration(scene: SceneScript) -> int:
        duration = max(2, math.ceil(scene.duration_seconds))
        if duration > 10:
            raise ValueError("gen4_turbo V1 scenes must be <= 10 seconds")
        return duration

    def estimate_video(self, scene: SceneScript) -> float:
        return self.billed_duration(scene) * self.cost_per_second_usd

    def create_video(self, scene: SceneScript, keyframe: ProviderOutput) -> ProviderOutput:
        if not keyframe.media_type.startswith("image/"):
            raise ValueError("Runway image-to-video requires an image keyframe")
        if not keyframe.payload:
            raise ValueError("Runway image-to-video requires non-empty keyframe bytes")
        if len(keyframe.payload) > self.max_inline_image_bytes:
            raise ValueError(
                "keyframe is too large for conservative data-URI upload; use owned HTTPS storage"
            )

        duration = self.billed_duration(scene)
        prompt_image = self._data_uri(keyframe)
        response = self.client.post(
            f"{self.config.base_url}/v1/image_to_video",
            headers=self._headers(),
            json={
                "model": self.config.model,
                "promptImage": prompt_image,
                "promptText": scene.video_prompt[:1000],
                "ratio": self.config.ratio,
                "duration": duration,
            },
        )
        self._raise_for_status(response, "create image-to-video task")
        task_id = str(response.json().get("id") or "")
        if not task_id:
            raise RunwayError("Runway create response did not contain a task id")

        task = self._wait_for_task(task_id)
        outputs = task.get("output") or []
        if not outputs or not isinstance(outputs[0], str):
            raise RunwayError(f"Runway task {task_id} succeeded without an output URL")

        media_response = self.client.get(outputs[0])
        self._raise_for_status(media_response, "download generated video")
        payload = media_response.content
        if not payload:
            raise RunwayError(f"Runway task {task_id} returned an empty video")

        cost = duration * self.cost_per_second_usd
        return ProviderOutput(
            provider=self.name,
            model=self.config.model,
            payload=payload,
            media_type="video/mp4",
            estimated_cost_usd=cost,
            actual_cost_usd=cost,
            provider_job_id=task_id,
        )

    def _wait_for_task(self, task_id: str) -> dict:
        deadline = time.monotonic() + self.config.timeout_seconds
        while time.monotonic() < deadline:
            response = self.client.get(
                f"{self.config.base_url}/v1/tasks/{task_id}",
                headers=self._headers(),
            )
            self._raise_for_status(response, "poll task")
            payload = response.json()
            status = str(payload.get("status") or "").upper()
            if status == "SUCCEEDED":
                return payload
            if status in {"FAILED", "CANCELED", "CANCELLED"}:
                raise RunwayError(f"Runway task {task_id} ended with status {status}")
            time.sleep(self.config.poll_interval_seconds)
        raise RunwayError(f"Runway task {task_id} timed out")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_secret}",
            "Content-Type": "application/json",
            "X-Runway-Version": self.config.api_version,
        }

    @staticmethod
    def _data_uri(keyframe: ProviderOutput) -> str:
        encoded = base64.b64encode(keyframe.payload).decode("ascii")
        return f"data:{keyframe.media_type};base64,{encoded}"

    @staticmethod
    def _raise_for_status(response: httpx.Response, action: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = response.text[:1000]
            raise RunwayError(
                f"Runway failed to {action}: HTTP {response.status_code}: {body}"
            ) from exc
