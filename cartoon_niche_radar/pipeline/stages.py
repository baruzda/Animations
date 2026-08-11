from __future__ import annotations

from typing import Any, Dict, Optional

from cartoon_niche_radar.storage.export import write_json
from cartoon_niche_radar.utils.config import get_collection_config, project_paths
from cartoon_niche_radar.utils.time import utcnow


def get_stage(name: str) -> Dict[str, Any]:
    stages = get_collection_config().get("stages", {})
    key = name.upper() if len(name) == 1 else name
    # accept A/B/C
    key = key if key in stages else name
    if key not in stages:
        raise ValueError(f"Unknown stage {name!r}. Expected one of {list(stages)}")
    cfg = dict(stages[key])
    cfg["id"] = key
    return cfg


def write_stage_qa(
    stage_id: str,
    *,
    sample_size: int,
    gates_passed: bool,
    composition: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Write per-stage QA report (no niche winner claims)."""
    stage = get_stage(stage_id)
    paths = project_paths()
    qa_dir = paths["qa"]
    qa_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "stage": stage["id"],
        "name": stage.get("name"),
        "purpose": stage.get("purpose"),
        "target_videos": stage.get("target_videos"),
        "generated_at": utcnow().isoformat(),
        "sample_size": sample_size,
        "gates_passed": gates_passed,
        "pass_criteria": {
            "A": "Schema + pipeline completeness; no winner declaration expected.",
            "B": "Strata composition visible; channel/theme caps not grossly violated.",
            "C": "Evidence gates for opportunity analysis; winners only if gates pass.",
        }.get(stage["id"], "See methodology."),
        "sample_composition": composition or {},
        "warnings": [
            "Do not declare best audience/niche from sample or incomplete live stages.",
            "Shorts opportunity analysis must use POST_2025_03_31 epoch.",
        ],
        "extra": extra or {},
        "ready_for_next_stage": bool(sample_size >= int(stage.get("target_videos", 0) * 0.9)),
    }
    write_json(qa_dir / f"stage_{stage['id']}_qa.json", report)
    md = [
        f"# Stage {stage['id']} QA — {stage.get('name')}",
        "",
        f"Purpose: {stage.get('purpose')}",
        f"Target videos: {stage.get('target_videos')}",
        f"Observed sample size: {sample_size}",
        f"Gates passed: {gates_passed}",
        f"Ready for next stage (size heuristic): {report['ready_for_next_stage']}",
        "",
        "## Warnings",
    ]
    for w in report["warnings"]:
        md.append(f"- {w}")
    (qa_dir / f"stage_{stage['id']}_qa.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return report
