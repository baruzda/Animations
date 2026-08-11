from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import typer
from rich.console import Console

from cartoon_factory.budget import BudgetGuard, BudgetPolicy
from cartoon_factory.domain.models import Episode, SceneScript
from cartoon_factory.domain.states import EpisodeState
from cartoon_factory.pipeline.core import FactoryPipeline
from cartoon_factory.providers.base import ProviderOutput
from cartoon_factory.providers.fakes import (
    FakeImageProvider,
    FakeObjectStore,
    FakeTextProvider,
    FakeVideoProvider,
    FakeVoiceProvider,
    LocalObjectStore,
)
from cartoon_factory.providers.runway import RunwayConfig, RunwayVideoProvider

app = typer.Typer(
    name="caf",
    help="CARTOON FACTORY — guarded AI cartoon production pipeline",
    add_completion=False,
)
console = Console()


def _fake_pipeline() -> FactoryPipeline:
    return FactoryPipeline(
        text=FakeTextProvider(),
        image=FakeImageProvider(),
        video=FakeVideoProvider(),
        voice=FakeVoiceProvider(),
        store=FakeObjectStore(),
    )


@app.command("smoke-fake")
def smoke_fake() -> None:
    """Run the complete V1 lifecycle with deterministic fake providers only."""
    pipeline = _fake_pipeline()
    episode = Episode()
    pipeline.build_preproduction(episode, "10 second limited-animation comedy short")
    pipeline.approve_production(episode)
    pipeline.render(episode)
    pipeline.assemble_manifest(episode)
    pipeline.run_qc(episode)
    pipeline.approve_final(episode)
    console.print(
        json.dumps(
            {
                "episode_id": episode.id,
                "state": episode.state.value,
                "estimated_cost_usd": round(episode.estimated_cost_usd, 4),
                "spent_cost_usd": round(episode.spent_cost_usd, 4),
                "assets": len(pipeline.assets),
                "cost_events": len(pipeline.cost_events),
                "qc_passed": all(result.passed for result in pipeline.qc_results),
                "real_paid_calls": 0,
            },
            indent=2,
        )
    )


@app.command("smoke-runway")
def smoke_runway(
    image: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
    prompt: str = typer.Option(
        "Clean limited animation, subtle readable movement, stable character design",
        help="Motion prompt for the one-scene smoke test",
    ),
    seconds: float = typer.Option(5.0, min=2.0, max=10.0),
    max_usd: float = typer.Option(0.50, min=0.01, max=1.00),
    confirm_paid: bool = typer.Option(
        False,
        "--confirm-paid",
        help="Required explicit acknowledgement that this command makes a paid API call",
    ),
) -> None:
    """Generate exactly one paid portrait Runway scene with a strict local hard cap."""
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    media_type = media_types.get(image.suffix.lower())
    if media_type is None:
        console.print("[red]Image must be PNG, JPEG or WebP.[/red]")
        raise typer.Exit(code=2)

    scene = SceneScript(
        index=1,
        duration_seconds=seconds,
        location="smoke-test",
        action="Animate the supplied keyframe according to the motion prompt.",
        camera="preserve composition",
        emotion="preserve source",
        video_prompt=prompt,
    )
    secret = os.getenv("RUNWAYML_API_SECRET", "")
    # A placeholder secret is sufficient for estimating. Network calls remain gated below.
    estimator = RunwayVideoProvider(RunwayConfig(api_secret=secret or "estimate-only"))
    estimated_usd = estimator.estimate_video(scene)

    if estimated_usd > max_usd:
        console.print(
            f"[red]Blocked before API call: estimated ${estimated_usd:.2f} exceeds "
            f"--max-usd ${max_usd:.2f}.[/red]"
        )
        raise typer.Exit(code=2)
    if not confirm_paid:
        console.print(
            f"Paid smoke is armed but NOT executed. Estimated maximum call cost: "
            f"${estimated_usd:.2f}. Re-run with --confirm-paid to execute exactly one scene."
        )
        raise typer.Exit(code=2)
    if not secret:
        console.print("[red]RUNWAYML_API_SECRET is missing. No API call was made.[/red]")
        raise typer.Exit(code=2)

    provider = RunwayVideoProvider(RunwayConfig(api_secret=secret))
    episode = Episode(state=EpisodeState.RENDERING)
    guard = BudgetGuard(
        BudgetPolicy(
            episode_soft_cap_usd=max_usd,
            episode_hard_cap_usd=max_usd,
            scene_retry_limit=0,
            max_parallel_video_jobs=1,
        )
    )
    event = guard.reserve(
        episode,
        provider=provider.name,
        operation="paid-smoke-video",
        estimated_usd=estimated_usd,
        scene_index=1,
    )
    keyframe = ProviderOutput(
        provider="local",
        model="user-keyframe",
        payload=image.read_bytes(),
        media_type=media_type,
    )
    output = provider.create_video(scene, keyframe)
    guard.reconcile(episode, event, output.actual_cost_usd)

    store = LocalObjectStore(Path("data/factory/paid-smoke"))
    storage_uri = store.put("runway-smoke.mp4", output.payload, output.media_type)
    console.print(
        json.dumps(
            {
                "provider": provider.name,
                "model": output.model,
                "provider_job_id": output.provider_job_id,
                "estimated_cost_usd": estimated_usd,
                "recorded_cost_usd": output.actual_cost_usd,
                "hard_cap_usd": max_usd,
                "storage_uri": storage_uri,
                "paid_calls": 1,
            },
            indent=2,
        )
    )


@app.command("doctor")
def doctor() -> None:
    """Check local production prerequisites without making paid API calls."""
    checks = {
        "ffmpeg": shutil.which("ffmpeg") or "missing",
        "ffprobe": shutil.which("ffprobe") or "missing",
        "openai_api_key": "configured" if os.getenv("OPENAI_API_KEY") else "missing",
        "runway_api_key": "configured" if os.getenv("RUNWAYML_API_SECRET") else "missing",
        "factory_database_url": "configured" if os.getenv("FACTORY_DATABASE_URL") else "missing",
        "r2_endpoint": "configured" if os.getenv("R2_ENDPOINT") else "missing",
        "local_asset_path": str(Path("data/factory/assets").resolve()),
        "paid_calls": "disabled",
    }
    for name, value in checks.items():
        console.print(f"{name}: {value}")


@app.command("status")
def status() -> None:
    """Show V1 implementation boundary."""
    console.print("Factory V1 core: available")
    console.print("Runway video adapter: available behind explicit paid-smoke confirmation")
    console.print("Persistence/API/dashboard: not enabled in core smoke")
    console.print("Use: caf smoke-fake")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
