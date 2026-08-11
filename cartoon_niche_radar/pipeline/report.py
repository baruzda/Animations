from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from cartoon_niche_radar.models.evidence import EvidenceKind
from cartoon_niche_radar.models.schemas import NicheScore, ReportBundle
from cartoon_niche_radar.storage.export import write_csv, write_json
from cartoon_niche_radar.utils.config import get_scoring_config, project_paths
from cartoon_niche_radar.utils.time import utcnow


REPORT_NAMES = [
    "best_age_group",
    "best_themes",
    "best_age_theme_combinations",
    "fastest_growing_formats",
    "most_saturated_niches",
    "underserved_niches",
    "successful_new_small_channels",
    "top_recurring_characters_formats",
    "dialogue_vs_no_dialogue",
    "music_vs_non_music",
    "optimal_duration",
    "best_themes_for_global_localization",
]


def _agg_metric(df: pd.DataFrame, group: str, metric: str = "views_per_day") -> list[dict[str, Any]]:
    if group not in df.columns or metric not in df.columns:
        return [{"status": "UNKNOWN", "reason": f"missing {group} or {metric}"}]
    rows = []
    for key, g in df.dropna(subset=[group]).groupby(group):
        s = g[metric].dropna()
        if s.empty:
            continue
        rows.append(
            {
                group: key,
                "n": int(len(g)),
                f"median_{metric}": float(s.median()),
                f"p90_{metric}": float(np.percentile(s, 90)),
                "kind": "INFERENCE",
            }
        )
    rows.sort(key=lambda r: r.get(f"median_{metric}", 0), reverse=True)
    return rows


def build_reports(
    df: pd.DataFrame,
    niches: list[NicheScore],
) -> dict[str, Any]:
    reports: dict[str, Any] = {}

    reports["best_age_group"] = _agg_metric(df, "target_age")
    reports["best_themes"] = _agg_metric(df, "theme")
    if "target_age" in df.columns and "theme" in df.columns:
        tmp = df.copy()
        tmp["age_theme"] = tmp["target_age"].astype(str) + " × " + tmp["theme"].astype(str)
        reports["best_age_theme_combinations"] = _agg_metric(tmp, "age_theme")
    else:
        reports["best_age_theme_combinations"] = [{"status": "UNKNOWN"}]

    reports["fastest_growing_formats"] = _agg_metric(df, "format", "views_per_day")

    scored = [n for n in niches if n.opportunity_score is not None]
    saturated = sorted(niches, key=lambda n: n.components.competition, reverse=True)[:20]
    reports["most_saturated_niches"] = [n.model_dump(mode="json") for n in saturated]

    underserved = [
        n
        for n in niches
        if not n.insufficient_data and n.components.competition < 0.4 and n.components.demand > 0.4
    ]
    underserved = sorted(
        underserved,
        key=lambda n: (n.opportunity_score or 0),
        reverse=True,
    )[:20]
    reports["underserved_niches"] = [n.model_dump(mode="json") for n in underserved]

    # Successful new/small channels
    if "channel_size_bucket" in df.columns and "channel_id" in df.columns:
        small = df[df["channel_size_bucket"].isin(["micro", "small"])]
        ch = (
            small.groupby("channel_id")
            .agg(
                median_views_per_day=("views_per_day", "median"),
                videos=("video_id", "count"),
                subscribers=("channel_subscribers", "max"),
            )
            .dropna()
            .sort_values("median_views_per_day", ascending=False)
            .head(50)
            .reset_index()
        )
        reports["successful_new_small_channels"] = {
            "kind": "INFERENCE",
            "rows": ch.to_dict(orient="records"),
            "note": "High views/day on micro/small channels — breakthrough lens.",
        }
    else:
        reports["successful_new_small_channels"] = {"status": "UNKNOWN"}

    reports["top_recurring_characters_formats"] = _agg_metric(df, "character_type")

    # Dialogue / music comparisons
    for field, name in [("dialogue", "dialogue_vs_no_dialogue"), ("music", "music_vs_non_music")]:
        if field in df.columns:
            tmp = df.copy()
            tmp[field] = tmp[field].map({True: f"{field}_yes", False: f"{field}_no"})
            reports[name] = _agg_metric(tmp, field)
        else:
            reports[name] = [{"status": "UNKNOWN"}]

    # Optimal duration from duration buckets / format
    reports["optimal_duration"] = _agg_metric(df, "format", "views_per_day")

    # Localization-friendly themes: prefer low dialogue if available
    if "theme" in df.columns:
        loc_rows = []
        for theme, g in df.dropna(subset=["theme"]).groupby("theme"):
            dialogue_rate = None
            if "dialogue" in g and g["dialogue"].notna().any():
                dialogue_rate = float(g["dialogue"].dropna().mean())
            med = g["views_per_day"].median() if "views_per_day" in g else None
            loc_rows.append(
                {
                    "theme": theme,
                    "n": int(len(g)),
                    "median_views_per_day": float(med) if med is not None and not pd.isna(med) else None,
                    "dialogue_rate": dialogue_rate,
                    "localization_proxy": None
                    if dialogue_rate is None
                    else float((1 - dialogue_rate) * (np.log1p(med or 0))),
                    "kind": "INFERENCE",
                }
            )
        loc_rows = [r for r in loc_rows if r["localization_proxy"] is not None]
        loc_rows.sort(key=lambda r: r["localization_proxy"], reverse=True)
        reports["best_themes_for_global_localization"] = loc_rows[:20]
    else:
        reports["best_themes_for_global_localization"] = [{"status": "UNKNOWN"}]

    reports["_scored_available"] = len(scored)
    return reports


def pick_highlights(niches: list[NicheScore]) -> dict[str, NicheScore | None]:
    scored = [n for n in niches if n.opportunity_score is not None and not n.insufficient_data]
    if not scored:
        return {
            "MOST_VIEWS": None,
            "BEST_MONEY_POTENTIAL": None,
            "EASIEST_TO_ENTER": None,
            "BEST_FOR_AI_PRODUCTION": None,
            "BEST_OVERALL": None,
        }

    most_views = max(scored, key=lambda n: n.median_views_per_day or 0)
    best_money = max(scored, key=lambda n: n.components.monetization)
    easiest = max(
        scored,
        key=lambda n: (1.0 - n.components.competition) * 0.7
        + (1.0 - n.components.production_complexity) * 0.3,
    )
    best_ai = min(scored, key=lambda n: n.components.production_complexity)
    best_overall = max(scored, key=lambda n: n.opportunity_score or 0)
    return {
        "MOST_VIEWS": most_views,
        "BEST_MONEY_POTENTIAL": best_money,
        "EASIEST_TO_ENTER": easiest,
        "BEST_FOR_AI_PRODUCTION": best_ai,
        "BEST_OVERALL": best_overall,
    }


def format_top20_block(n: NicheScore) -> dict[str, Any]:
    return {
        "AGE": n.niche.age,
        "THEME": n.niche.theme,
        "FORMAT": n.niche.format,
        "LANGUAGE": n.niche.language,
        "CHARACTER": n.niche.character,
        "DEMAND": round(n.components.demand, 4),
        "COMPETITION": round(n.components.competition, 4),
        "MEDIAN_VIEWS_PER_DAY": n.median_views_per_day,
        "P90_VIEWS_PER_DAY": n.p90_views_per_day,
        "MONETIZATION_SCORE": round(n.components.monetization, 4),
        "OPPORTUNITY_SCORE": None
        if n.opportunity_score is None
        else round(n.opportunity_score, 4),
        "CONFIDENCE": round(n.confidence, 4),
        "N_VIDEOS": n.n_videos,
        "N_CHANNELS": n.n_channels,
        "EVIDENCE": n.evidence_status.value,
        "INSUFFICIENT_DATA": n.insufficient_data,
    }


def sample_composition(df: pd.DataFrame) -> dict[str, Any]:
    """Report dataset composition across required strata."""
    out: dict[str, Any] = {"n": int(len(df)), "kind": "FACT_counts_INFERENCE_labels"}
    for col in [
        "target_age",
        "theme",
        "channel_size_bucket",
        "language",
        "short_or_long",
        "views_metric_epoch",
        "made_for_kids",
        "youtube_content_type",
        "sample_role",
        "duration_bin",
        "source_seed_family",
    ]:
        if col in df.columns:
            out[col] = {str(k): int(v) for k, v in df[col].fillna("UNKNOWN").value_counts().items()}
    if "sample_role" in df.columns:
        core = df[df["sample_role"].fillna("CORE") == "CORE"]
        cov = df[df["sample_role"] == "COVERAGE"]
        out["core_vs_coverage"] = {
            "CORE": int(len(core)),
            "COVERAGE": int(len(cov)),
            "note": "COVERAGE must not silently weight unweighted CORE age-demand comparisons.",
        }
    if "publish_date" in df.columns:
        try:
            ages = pd.to_datetime(df["publish_date"], utc=True, errors="coerce")
            days = (pd.Timestamp.utcnow() - ages).dt.total_seconds() / 86400.0
            bins = [0, 7, 30, 90, 365, 1e9]
            labels = ["0-7d", "8-30d", "31-90d", "91-365d", "365d+"]
            out["publication_age"] = {
                str(k): int(v)
                for k, v in pd.cut(days, bins=bins, labels=labels).value_counts().items()
            }
        except Exception:  # noqa: BLE001
            out["publication_age"] = {"status": "UNKNOWN"}
    return out


def strata_coverage_ratio(composition: dict[str, Any], required: list[str]) -> float:
    present = 0
    for key in required:
        block = composition.get(key)
        if isinstance(block, dict) and any(int(v) > 0 for v in block.values() if str(v).isdigit() or isinstance(v, int)):
            present += 1
        elif isinstance(block, dict) and len(block) > 0:
            present += 1
    return present / max(1, len(required))


def run_report(
    df: pd.DataFrame,
    niches: list[NicheScore],
) -> ReportBundle:
    paths = project_paths()
    cfg = get_scoring_config()
    gates = cfg.get("evidence_gates", {})
    sample_size = int(len(df))
    composition = sample_composition(df)
    coverage = strata_coverage_ratio(
        composition,
        ["target_age", "theme", "channel_size_bucket", "publication_age", "language", "short_or_long"],
    )

    gates_passed = (
        sample_size >= int(gates.get("min_videos_total", 1000))
        and coverage >= float(gates.get("min_strata_coverage_ratio", 0.5))
    )

    # Opportunity reports should prefer post-epoch rows when available
    report_df = df
    if "opportunity_eligible" in df.columns:
        eligible = df[df["opportunity_eligible"] == True]  # noqa: E712
        if len(eligible) > 0:
            report_df = eligible

    reports = build_reports(report_df, niches)
    # Also attach PRE-epoch descriptive block separately
    if "views_metric_epoch" in df.columns:
        pre = df[df["views_metric_epoch"] == "PRE_2025_03_31"]
        reports["pre_epoch_shorts_descriptive"] = {
            "kind": "FACT_separation",
            "n": int(len(pre)),
            "note": "PRE_2025_03_31 Shorts excluded from opportunity median/viral mixing.",
            "best_age_group": _agg_metric(pre, "target_age") if len(pre) else [],
        }

    highlights = pick_highlights(niches)
    scored = [n for n in niches if n.opportunity_score is not None and not n.insufficient_data]
    scored = sorted(scored, key=lambda n: n.opportunity_score or 0, reverse=True)
    top20 = scored[:20]

    caveats = list(cfg.get("methodology_warnings") or [])
    caveats += [
        "FACT/INFERENCE/UNKNOWN are explicit in outputs; opportunity scores are INFERENCE.",
        "Do not declare a commercial winner if evidence gates fail.",
        "Do not preferentially elevate age 13–17 unless scores + gates support it.",
        "TikTok Research API excluded (commercial use prohibited under current ToS).",
        "Google Trends is a secondary signal only.",
        f"Sample strata coverage ratio: {coverage:.2f}.",
    ]
    if not gates_passed:
        caveats.append(
            f"INSUFFICIENT_DATA: sample_size={sample_size} < min_videos_total="
            f"{gates.get('min_videos_total')} or strata coverage below threshold. "
            "No BEST_OVERALL declaration."
        )
        highlights = {k: None for k in highlights}

    age_rows = reports.get("best_age_group") or []
    caveats.append(
        "Bias guard: watched hypothesis age is 13–17; compare all age clusters empirically."
    )
    if age_rows and isinstance(age_rows, list) and age_rows and "target_age" in age_rows[0]:
        leader = age_rows[0].get("target_age")
        caveats.append(
            f"Current POST-epoch age leader by median views/day (INFERENCE, not declared winner): {leader}"
        )

    bundle = ReportBundle(
        generated_at=utcnow(),
        sample_size=sample_size,
        evidence_gates_passed=gates_passed,
        reports={k: reports.get(k) for k in REPORT_NAMES},
        top20=top20,
        highlights=highlights,
        caveats=caveats,
        sample_composition=composition,
    )

    out_dir = paths["reports"]
    write_json(out_dir / "report_bundle.json", bundle.model_dump(mode="json"))
    write_csv(out_dir / "top20_niches.csv", [format_top20_block(n) for n in top20])
    write_json(out_dir / "top20_niches.json", [format_top20_block(n) for n in top20])
    write_json(
        out_dir / "highlights.json",
        {k: (None if v is None else format_top20_block(v)) for k, v in highlights.items()},
    )
    write_json(out_dir / "sample_composition.json", composition)
    (out_dir / "SUMMARY.md").write_text(render_markdown(bundle), encoding="utf-8")
    return bundle


def render_markdown(bundle: ReportBundle) -> str:
    lines = [
        "# CARTOON NICHE RADAR — Report",
        "",
        f"Generated: {bundle.generated_at.isoformat()}",
        f"Sample size: {bundle.sample_size}",
        f"Evidence gates passed: {bundle.evidence_gates_passed}",
        "",
        "## Methodology warnings",
        "",
    ]
    for c in bundle.caveats:
        lines.append(f"- {c}")
    lines += ["", "## Sample composition", ""]
    for key, val in (bundle.sample_composition or {}).items():
        if key == "n":
            lines.append(f"- n: {val}")
        elif isinstance(val, dict):
            lines.append(f"- {key}: {val}")
    lines += ["", "## Highlights", ""]
    for name, niche in bundle.highlights.items():
        if niche is None:
            lines.append(f"- **{name}**: INSUFFICIENT_DATA / not declared")
        else:
            block = format_top20_block(niche)
            lines.append(
                f"- **{name}**: AGE {block['AGE']} | THEME {block['THEME']} | "
                f"OPP {block['OPPORTUNITY_SCORE']} | CONF {block['CONFIDENCE']}"
            )
    lines += ["", "## TOP-20 niches", ""]
    if not bundle.top20:
        lines.append("_No niches passed evidence gates._")
    for i, n in enumerate(bundle.top20, 1):
        b = format_top20_block(n)
        lines += [
            f"### {i}. {b['AGE']} · {b['THEME']}",
            f"- FORMAT: {b['FORMAT']}",
            f"- LANGUAGE: {b['LANGUAGE']}",
            f"- CHARACTER: {b['CHARACTER']}",
            f"- DEMAND: {b['DEMAND']}",
            f"- COMPETITION: {b['COMPETITION']}",
            f"- MEDIAN VIEWS/DAY: {b['MEDIAN_VIEWS_PER_DAY']}",
            f"- P90 VIEWS/DAY: {b['P90_VIEWS_PER_DAY']}",
            f"- MONETIZATION SCORE: {b['MONETIZATION_SCORE']}",
            f"- OPPORTUNITY SCORE: {b['OPPORTUNITY_SCORE']}",
            f"- CONFIDENCE: {b['CONFIDENCE']}",
            "",
        ]
    return "\n".join(lines)
