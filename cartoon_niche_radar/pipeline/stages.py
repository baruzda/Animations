from __future__ import annotations

from typing import Any, Dict, Optional

from cartoon_niche_radar.storage.export import write_json
from cartoon_niche_radar.utils.config import get_collection_config, project_paths
from cartoon_niche_radar.utils.time import utcnow


def get_stage(name: str) -> Dict[str, Any]:
    stages = get_collection_config().get("stages", {})
    key = name.upper() if len(name) == 1 else name
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
    query_plan: Optional[Dict[str, Any]] = None,
    readiness: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    stage = get_stage(stage_id)
    paths = project_paths()
    qa_dir = paths["qa"]
    qa_dir.mkdir(parents=True, exist_ok=True)

    plan = query_plan or {}
    report = {
        "stage": stage["id"],
        "name": stage.get("name"),
        "purpose": stage.get("purpose"),
        "target_videos": stage.get("target_videos"),
        "generated_at": utcnow().isoformat(),
        "sample_size": sample_size,
        "gates_passed": gates_passed,
        "planned_search_calls": plan.get("planned_search_calls"),
        "executed_search_calls": plan.get("executed_search_calls"),
        "publishedAfter": plan.get("publishedAfter"),
        "lookback_days": plan.get("lookback_days"),
        "coverage_by_dimension": plan.get("coverage_by_dimension"),
        "omitted_dimensions": plan.get("omitted_dimensions"),
        "pass_criteria": {
            "A": "Schema + pipeline completeness; no winner declaration expected.",
            "B": "Strata composition visible; classifier validation required before C.",
            "C": "Evidence gates + classifier validation; winners only if gates pass.",
        }.get(stage["id"], "See methodology."),
        "sample_composition": composition or {},
        "warnings": [
            "Do not declare best audience/niche from sample or incomplete live stages.",
            "Shorts opportunity analysis requires SHORTS_CONFIRMED (or high-conf inferred) POST_2025_03_31.",
            "search.list videoDuration=short is NOT Shorts confirmation.",
            "COVERAGE seeds must not silently weight CORE age-demand comparisons.",
        ],
        "extra": extra or {},
        "readiness": readiness or {},
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
        f"planned_search_calls: {report['planned_search_calls']}",
        f"executed_search_calls: {report['executed_search_calls']}",
        f"publishedAfter: {report['publishedAfter']}",
        f"Ready for next stage (size heuristic): {report['ready_for_next_stage']}",
        "",
        "## Warnings",
    ]
    for w in report["warnings"]:
        md.append(f"- {w}")
    (qa_dir / f"stage_{stage['id']}_qa.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return report


def readiness_verdict(
    *,
    collector_ok: bool,
    classifier_ok: bool,
    sampling_ok: bool,
    empirical_ok: bool = False,
) -> Dict[str, Any]:
    stage_a = bool(collector_ok and classifier_ok and sampling_ok)
    return {
        "COLLECTOR_READY_STAGE_A": collector_ok,
        "CLASSIFIER_READY_STAGE_A": classifier_ok,
        "SAMPLING_READY_STAGE_A": sampling_ok,
        "EMPIRICAL_ANALYSIS_READY": empirical_ok,
        "STAGE_A_READY": "YES" if stage_a else "NO",
        "note": "EMPIRICAL_ANALYSIS_READY requires live Stage C + gates + classifier validation.",
    }
