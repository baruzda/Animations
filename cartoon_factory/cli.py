from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import typer
from rich.console import Console

from cartoon_factory.domain.models import Episode
from cartoon_factory.pipeline.core import FactoryPipeline
from cartoon_factory.providers.fakes import (
    FakeImageProvider,
    FakeObjectStore,
    FakeTextProvider,
    FakeVideoProvider,
    FakeVoiceProvider,
)

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
    console.print("Persistence/API/real media adapters: not enabled in core smoke")
    console.print("Use: caf smoke-fake")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
