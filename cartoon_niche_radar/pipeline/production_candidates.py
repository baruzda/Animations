from __future__ import annotations

from pathlib import Path
from typing import Any

import orjson

from cartoon_niche_radar.models.schemas import NicheScore
from cartoon_niche_radar.storage.export import write_json
from cartoon_niche_radar.utils.config import project_paths


class ProductionCandidateGateError(RuntimeError):
    """Raised when a Radar run is not safe to feed into production."""


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise ProductionCandidateGateError(f"required Radar artifact is missing: {path}")
    return orjson.loads(path.read_bytes())


def export_production_candidates(
    *,
    min_confidence: float = 0.65,
    top_n: int = 20,
) -> dict[str, Any]:
    """Export only evidence-gated, non-synthetic Radar niches for Factory.

    This is intentionally fail-closed. A synthetic/sample run or a run whose
    evidence gates failed produces no production candidates.
    """
    if not 0 <= min_confidence <= 1:
        raise ValueError("min_confidence must be between 0 and 1")
    if top_n < 1:
        raise ValueError("top_n must be >= 1")

    paths = project_paths()
    last_run = _read_json(paths["outputs"] / "last_run.json")
    scores_raw = _read_json(paths["scored"] / "niche_scores.json")

    if bool(last_run.get("synthetic", False)):
        raise ProductionCandidateGateError(
            "last Radar run is synthetic/sample data; production export is forbidden"
        )
    if not bool(last_run.get("gates_passed", False)):
        raise ProductionCandidateGateError(
            "last Radar run did not pass evidence gates; production export is forbidden"
        )

    generated_at = str(last_run.get("generated_at") or "UNKNOWN")
    stage = str(last_run.get("stage") or "UNSTAGED")
    radar_run_id = f"{stage}:{generated_at}"

    niches = [NicheScore.model_validate(item) for item in scores_raw]
    eligible = [
        niche
        for niche in niches
        if not niche.insufficient_data
        and niche.opportunity_score is not None
        and niche.confidence >= min_confidence
    ]
    eligible.sort(key=lambda item: float(item.opportunity_score or 0), reverse=True)

    candidates = []
    for niche in eligible[:top_n]:
        candidates.append(
            {
                "radar_run_id": radar_run_id,
                "generated_at": generated_at,
                "niche_key": niche.niche.label(),
                "opportunity_score": niche.opportunity_score,
                "confidence": niche.confidence,
                "evidence_status": niche.evidence_status.value,
                "insufficient_data": niche.insufficient_data,
                "evidence_gates_passed": True,
                "synthetic": False,
                "components": niche.components.model_dump(mode="json"),
                "n_videos": niche.n_videos,
                "n_channels": niche.n_channels,
            }
        )

    payload = {
        "radar_run_id": radar_run_id,
        "generated_at": generated_at,
        "min_confidence": min_confidence,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    write_json(paths["reports"] / "production_candidates.json", payload)
    return payload
