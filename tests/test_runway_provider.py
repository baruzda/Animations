from __future__ import annotations

import httpx
import pytest

from cartoon_factory.domain.models import SceneScript
from cartoon_factory.providers.base import ProviderOutput
from cartoon_factory.providers.runway import RunwayConfig, RunwayVideoProvider


def scene(duration: float = 4.2) -> SceneScript:
    return SceneScript(
        index=1,
        duration_seconds=duration,
        location="hallway",
        action="Miko reaches for the door handle.",
        camera="medium close-up",
        emotion="curious",
        video_prompt="Clean limited animation, subtle character movement, portrait composition",
    )


def test_runway_estimate_uses_billed_integer_seconds() -> None:
    provider = RunwayVideoProvider(RunwayConfig(api_secret="test-secret"))
    assert provider.estimate_video(scene(4.2)) == pytest.approx(0.25)
    assert provider.estimate_video(scene(2.0)) == pytest.approx(0.10)


def test_runway_rejects_scene_longer_than_v1_limit() -> None:
    provider = RunwayVideoProvider(RunwayConfig(api_secret="test-secret"))
    with pytest.raises(ValueError, match="<= 10"):
        provider.estimate_video(scene(10.5))


def test_runway_provider_downloads_ephemeral_output_immediately() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url}")
        if request.url.path == "/v1/image_to_video":
            assert request.headers["Authorization"] == "Bearer test-secret"
            assert request.headers["X-Runway-Version"] == "2024-11-06"
            return httpx.Response(200, json={"id": "task-1"})
        if request.url.path == "/v1/tasks/task-1":
            return httpx.Response(
                200,
                json={
                    "id": "task-1",
                    "status": "SUCCEEDED",
                    "output": ["https://cdn.example/output.mp4"],
                },
            )
        if request.url.host == "cdn.example":
            return httpx.Response(200, content=b"fake-mp4-bytes")
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = RunwayVideoProvider(
        RunwayConfig(api_secret="test-secret", poll_interval_seconds=0.0),
        client=client,
    )
    keyframe = ProviderOutput(
        provider="fake-image",
        model="fake",
        payload=b"fake-png-bytes",
        media_type="image/png",
    )

    output = provider.create_video(scene(5), keyframe)

    assert output.provider_job_id == "task-1"
    assert output.payload == b"fake-mp4-bytes"
    assert output.actual_cost_usd == pytest.approx(0.25)
    assert len(calls) == 3
