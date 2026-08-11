from __future__ import annotations

import orjson
import pandas as pd
import typer
from rich.console import Console

from cartoon_niche_radar.pipeline.classify import run_classify
from cartoon_niche_radar.pipeline.collect import run_collect
from cartoon_niche_radar.pipeline.normalize import run_normalize
from cartoon_niche_radar.pipeline.production_candidates import (
    ProductionCandidateGateError,
    export_production_candidates,
)
from cartoon_niche_radar.pipeline.report import run_report
from cartoon_niche_radar.pipeline.score import build_analysis_frame, run_score
from cartoon_niche_radar.pipeline.stages import get_stage, readiness_verdict, write_stage_qa
from cartoon_niche_radar.pipeline.validation import run_classifier_validation
from cartoon_niche_radar.storage.export import write_json
from cartoon_niche_radar.utils.config import clear_config_caches, project_paths

app = typer.Typer(
    name="cnr",
    help="CARTOON NICHE RADAR — empirical AI cartoon niche research pipeline",
    add_completion=False,
)
console = Console()


@app.command("collect")
def collect_cmd(
    max_videos: int = typer.Option(500, help="Target videos for this run (default Stage A size)"),
    dry_run: bool = typer.Option(False, help="Skip YouTube API calls"),
    stage: str = typer.Option("", help="Staged protocol: A | B | C"),
    discover_only: bool = typer.Option(False, help="Discovery phase only (no enrichment)"),
    enrich_only: bool = typer.Option(False, help="Enrichment phase only (known IDs)"),
) -> None:
    """Phase 1 — resume-safe collect (discover ≠ enrich)."""
    meta = run_collect(
        max_videos=max_videos,
        dry_run=dry_run,
        stage=stage or None,
        discover_only=discover_only,
        enrich_only=enrich_only,
    )
    console.print(meta)


@app.command("normalize")
def normalize_cmd() -> None:
    """Phase 3 — normalize metrics (views/day etc.)."""
    df = run_normalize()
    console.print(f"Normalized rows: {len(df)}")


@app.command("classify")
def classify_cmd() -> None:
    """Phase 4 — AI/heuristic classification with confidence."""
    out = run_classify()
    console.print(f"Classified: {len(out)}")


@app.command("score")
def score_cmd() -> None:
    """Phase 5 — commercial / opportunity scores."""
    paths = project_paths()
    norm = pd.read_csv(paths["normalized"] / "videos_normalized.csv")
    clf_path = paths["classified"] / "classifications.jsonl"
    classifications = [orjson.loads(line) for line in clf_path.open("rb")]
    niches = run_score(norm, classifications)
    console.print(f"Niches scored: {len(niches)}")


@app.command("report")
def report_cmd() -> None:
    """Phase 6 — dashboards inputs + TOP-20 + CSV/JSON."""
    paths = project_paths()
    norm = pd.read_csv(paths["normalized"] / "videos_normalized.csv")
    clf_path = paths["classified"] / "classifications.jsonl"
    classifications = [orjson.loads(line) for line in clf_path.open("rb")]
    df = build_analysis_frame(norm, classifications)
    scores = orjson.loads((paths["scored"] / "niche_scores.json").read_bytes())
    from cartoon_niche_radar.models.schemas import NicheScore

    niches = [NicheScore.model_validate(x) for x in scores]
    bundle = run_report(df, niches)
    console.print(f"Report written. gates_passed={bundle.evidence_gates_passed}")


@app.command("production-candidates")
def production_candidates_cmd(
    min_confidence: float = typer.Option(0.65, help="Minimum Radar confidence for production"),
    top_n: int = typer.Option(20, help="Maximum production candidates to export"),
) -> None:
    """Export a fail-closed Radar → Factory candidate bundle."""
    try:
        payload = export_production_candidates(
            min_confidence=min_confidence,
            top_n=top_n,
        )
    except ProductionCandidateGateError as exc:
        console.print(f"[red]Production export blocked: {exc}[/red]")
        raise typer.Exit(code=2) from exc
    paths = project_paths()
    console.print(
        f"Production candidates: {payload['candidate_count']} — "
        f"{paths['reports'] / 'production_candidates.json'}"
    )


@app.command("run-all")
def run_all_cmd(
    max_videos: int = typer.Option(500, help="Target videos (prefer staged protocol)"),
    dry_run: bool = typer.Option(False, help="Skip live API collection"),
    use_sample: bool = typer.Option(
        False,
        help="Use synthetic sample dataset (for pipeline validation without API key)",
    ),
    stage: str = typer.Option("", help="Staged protocol: A | B | C"),
) -> None:
    """Run phases 1→6 end-to-end."""
    clear_config_caches()
    paths = project_paths()
    stage_id = stage.upper() if stage else None
    if stage_id:
        stage_cfg = get_stage(stage_id)
        max_videos = int(stage_cfg["target_videos"])

    if use_sample:
        from cartoon_niche_radar.pipeline.sample import generate_sample

        generate_sample(n=min(max_videos, 500) if not stage_id else min(max_videos, 500))
        console.print("[yellow]Using synthetic sample (NOT empirical FACT for niches).[/yellow]")
    else:
        run_collect(max_videos=max_videos, dry_run=dry_run, stage=stage_id)
        if dry_run:
            console.print("[red]Dry run stopped before normalize/score (no videos).[/red]")
            raise typer.Exit(code=0)

    df_norm = run_normalize()
    classifications = run_classify()
    niches = run_score(df_norm, classifications)
    df = build_analysis_frame(df_norm, classifications)
    bundle = run_report(df, niches)
    validation = run_classifier_validation(classifications)

    readiness = readiness_verdict(
        collector_ok=True,
        classifier_ok=True,
        sampling_ok=True,
        empirical_ok=False,
    )
    if stage_id:
        write_stage_qa(
            stage_id,
            sample_size=bundle.sample_size,
            gates_passed=bundle.evidence_gates_passed,
            composition=bundle.sample_composition,
            extra={
                "top20_count": len(bundle.top20),
                "synthetic": use_sample,
                "classifier_validation": validation,
            },
            readiness=readiness,
        )

    write_json(
        paths["outputs"] / "last_run.json",
        {
            "generated_at": bundle.generated_at.isoformat(),
            "synthetic": use_sample,
            "sample_size": bundle.sample_size,
            "gates_passed": bundle.evidence_gates_passed,
            "top20_count": len(bundle.top20),
            "stage": stage_id,
            "readiness": readiness,
            "highlights_declared": {
                k: v is not None for k, v in bundle.highlights.items()
            },
        },
    )
    console.print("[green]Pipeline complete.[/green]")
    console.print(f"Summary: {paths['reports'] / 'SUMMARY.md'}")
    console.print(readiness)


@app.command("status")
def status_cmd() -> None:
    """Show local dataset / report / resume status."""
    paths = project_paths()
    checks = {
        "raw_videos": paths["raw"] / "youtube_videos.jsonl",
        "collection_state": paths["raw"] / "collection_state.json",
        "quota_calls": paths["raw"] / "quota_calls.jsonl",
        "normalized": paths["normalized"] / "videos_normalized.csv",
        "classified": paths["classified"] / "classifications.jsonl",
        "scored": paths["scored"] / "niche_scores.json",
        "summary": paths["reports"] / "SUMMARY.md",
        "sample_composition": paths["reports"] / "sample_composition.json",
        "production_candidates": paths["reports"] / "production_candidates.json",
    }
    for name, path in checks.items():
        console.print(f"{name}: {'OK' if path.exists() else 'missing'} — {path}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
