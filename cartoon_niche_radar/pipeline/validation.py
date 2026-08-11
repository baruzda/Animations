from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from cartoon_niche_radar.storage.export import write_json
from cartoon_niche_radar.utils.config import get_collection_config, project_paths
from cartoon_niche_radar.utils.time import utcnow


def load_gold_sample(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    cfg = get_collection_config().get("classifier", {}).get("validation", {})
    rel = cfg.get("gold_sample_path", "data/validation/gold_sample.jsonl")
    gold_path = path or (project_paths()["root"] / rel)
    if not gold_path.exists():
        return []
    rows = []
    for line in gold_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def evaluate_classifier(
    predictions: List[Dict[str, Any]],
    gold: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compare classifier outputs to stratified gold labels."""
    by_id = {p["video_id"]: p for p in predictions if "video_id" in p}
    age_correct = age_total = 0
    theme_correct = theme_total = 0
    unknown_age = 0
    confidences: List[float] = []

    for g in gold:
        vid = g["video_id"]
        pred = by_id.get(vid)
        if not pred:
            continue
        age_field = pred.get("target_age") or {}
        theme_field = pred.get("theme") or {}
        age_val = age_field.get("value") if isinstance(age_field, dict) else age_field
        theme_val = theme_field.get("value") if isinstance(theme_field, dict) else theme_field
        age_kind = age_field.get("kind") if isinstance(age_field, dict) else None
        if age_kind == "UNKNOWN" or age_val is None:
            unknown_age += 1
        if g.get("target_age"):
            age_total += 1
            if age_val == g["target_age"]:
                age_correct += 1
            confidences.append(float((age_field or {}).get("confidence") or 0))
        if g.get("theme"):
            theme_total += 1
            if theme_val == g["theme"]:
                theme_correct += 1

    n = max(1, len(gold))
    report = {
        "generated_at": utcnow().isoformat(),
        "n_gold": len(gold),
        "n_matched_predictions": sum(1 for g in gold if g["video_id"] in by_id),
        "age_accuracy": (age_correct / age_total) if age_total else None,
        "theme_accuracy": (theme_correct / theme_total) if theme_total else None,
        "unknown_rate": unknown_age / n,
        "mean_age_confidence": (sum(confidences) / len(confidences)) if confidences else None,
        "kind": "INFERENCE_validation_metrics",
    }
    return report


def validation_gate(report: Dict[str, Any]) -> Dict[str, Any]:
    cfg = get_collection_config().get("classifier", {}).get("validation", {})
    if not cfg.get("enabled", True):
        return {"passed": True, "reason": "validation disabled", "report": report}
    if report.get("n_gold", 0) == 0:
        return {
            "passed": False,
            "reason": "NO_GOLD_SAMPLE",
            "block_stage_c": bool(cfg.get("block_stage_c_on_failure", True)),
            "report": report,
        }
    checks = {
        "age_accuracy": (report.get("age_accuracy") or 0) >= float(cfg.get("min_age_accuracy", 0.65)),
        "theme_accuracy": (report.get("theme_accuracy") or 0)
        >= float(cfg.get("min_theme_accuracy", 0.65)),
        "unknown_rate": (report.get("unknown_rate") or 1) <= float(cfg.get("max_unknown_rate", 0.40)),
    }
    passed = all(checks.values())
    return {
        "passed": passed,
        "checks": checks,
        "block_stage_c": bool(cfg.get("block_stage_c_on_failure", True)) and not passed,
        "report": report,
    }


def run_classifier_validation(predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
    gold = load_gold_sample()
    report = evaluate_classifier(predictions, gold)
    gate = validation_gate(report)
    cfg = get_collection_config().get("classifier", {}).get("validation", {})
    out = project_paths()["root"] / cfg.get(
        "report_path", "data/reports/qa/classifier_validation.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json(out, gate)
    return gate
