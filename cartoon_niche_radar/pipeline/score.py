from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from cartoon_niche_radar.models.evidence import EvidenceKind
from cartoon_niche_radar.models.schemas import ComponentScores, NicheKey, NicheScore
from cartoon_niche_radar.storage.export import write_csv, write_json
from cartoon_niche_radar.utils.config import get_scoring_config, project_paths


def _percentile(series: pd.Series, q: float) -> float | None:
    s = series.dropna()
    if s.empty:
        return None
    return float(np.percentile(s.to_numpy(), q))


def _minmax(series: pd.Series) -> pd.Series:
    s = series.astype(float)
    lo, hi = s.min(), s.max()
    if pd.isna(lo) or pd.isna(hi) or hi == lo:
        return pd.Series([0.5] * len(s), index=s.index)
    return (s - lo) / (hi - lo)


def _evidenced_value(cell: Any) -> Any:
    if isinstance(cell, dict):
        if cell.get("kind") == EvidenceKind.UNKNOWN.value:
            return None
        if float(cell.get("confidence") or 0) <= 0:
            return None
        return cell.get("value")
    return cell


def build_analysis_frame(
    normalized: pd.DataFrame,
    classifications: list[dict[str, Any]],
) -> pd.DataFrame:
    cdf = pd.DataFrame(classifications)
    if cdf.empty:
        raise ValueError("No classifications available")

    for col in [
        "target_age",
        "theme",
        "format",
        "character_type",
        "dialogue",
        "music",
        "visual_style",
    ]:
        if col in cdf.columns:
            cdf[col] = cdf[col].map(_evidenced_value)

    conf_by_id: dict[str, float] = {}
    for item in classifications:
        confs = []
        for key in ("target_age", "theme", "format", "visual_style"):
            field = item.get(key) or {}
            if isinstance(field, dict) and field.get("kind") != EvidenceKind.UNKNOWN.value:
                confs.append(float(field.get("confidence") or 0))
        conf_by_id[item["video_id"]] = float(np.mean(confs)) if confs else 0.0

    cdf["clf_confidence"] = cdf["video_id"].map(conf_by_id)
    keep = [
        c
        for c in [
            "video_id",
            "target_age",
            "theme",
            "format",
            "character_type",
            "dialogue",
            "music",
            "visual_style",
            "clf_confidence",
        ]
        if c in cdf.columns
    ]
    merged = normalized.merge(cdf[keep], on="video_id", how="inner")
    return merged


def score_niches(
    df: pd.DataFrame,
    trends_by_theme: dict[str, float] | None = None,
) -> list[NicheScore]:
    cfg = get_scoring_config()
    gates = cfg.get("evidence_gates", {})
    weights = cfg.get("opportunity_weights", {})
    trends_by_theme = trends_by_theme or {}

    work = df.copy()
    # Primary opportunity path: confirmed/high-conf Shorts POST epoch only
    if "opportunity_eligible" in work.columns:
        opp = work[work["opportunity_eligible"] == True].copy()  # noqa: E712
    elif "views_metric_epoch" in work.columns and "youtube_content_type" in work.columns:
        primary = cfg.get("normalization", {}).get("shorts_opportunity_epoch", "POST_2025_03_31")
        opp = work[
            (work["views_metric_epoch"] == primary)
            & (work["youtube_content_type"] == "SHORTS_CONFIRMED")
        ].copy()
    elif "views_metric_epoch" in work.columns:
        primary = cfg.get("normalization", {}).get("shorts_opportunity_epoch", "POST_2025_03_31")
        opp = work[work["views_metric_epoch"] == primary].copy()
    else:
        opp = work

    # Age-demand comparisons must not silently include COVERAGE-targeted recall
    if "sample_role" in opp.columns:
        core_opp = opp[opp["sample_role"].fillna("CORE") == "CORE"].copy()
        work = core_opp if len(core_opp) > 0 else opp
    else:
        work = opp
    work["age"] = work.get("target_age").fillna("UNKNOWN") if "target_age" in work else "UNKNOWN"
    work["theme"] = work.get("theme").fillna("UNKNOWN") if "theme" in work else "UNKNOWN"
    work["format"] = work.get("format").fillna("UNKNOWN") if "format" in work else "UNKNOWN"
    work["language"] = work.get("language").fillna("unknown") if "language" in work else "unknown"
    work["character"] = (
        work.get("character_type").fillna("unknown") if "character_type" in work else "unknown"
    )

    ranked = work[
        (work["age"] != "UNKNOWN")
        & (work["theme"] != "UNKNOWN")
        & (work["theme"] != "other")
        & (work["format"] != "UNKNOWN")
    ].copy()

    niches: list[NicheScore] = []
    if ranked.empty:
        return niches

    group_cols = ["age", "theme", "format", "language", "character"]
    for keys, g in ranked.groupby(group_cols, dropna=False):
        age, theme, fmt, lang, character = keys
        n_videos = len(g)
        n_channels = g["channel_id"].nunique() if "channel_id" in g else 0
        max_ch_share = 0.0
        if "channel_id" in g and n_videos > 0:
            max_ch_share = float(g["channel_id"].value_counts(normalize=True).max())

        # UNKNOWN rate among age/theme labels in the parent frame for this niche keys
        unknown_rate = 0.0
        if "clf_confidence" in g:
            unknown_rate = float((g["clf_confidence"] <= 0).mean())

        med_vpd = _percentile(g["views_per_day"], 50) if "views_per_day" in g else None
        p90_vpd = _percentile(g["views_per_day"], 90) if "views_per_day" in g else None
        med_eng = _percentile(g["engagement_rate"], 50) if "engagement_rate" in g else None
        med_like = _percentile(g["like_rate"], 50) if "like_rate" in g else None
        med_comment = _percentile(g["comment_rate"], 50) if "comment_rate" in g else None
        med_viral = _percentile(g["viral_coefficient"], 50) if "viral_coefficient" in g else None
        med_conf = float(g["clf_confidence"].median()) if "clf_confidence" in g else 0.0

        mega_share = 0.0
        if "channel_size_bucket" in g:
            mega_share = float((g["channel_size_bucket"] == "mega").mean())
        density = float(n_videos)

        trend = float(trends_by_theme.get(str(theme), 0.0))
        demand_raw = (
            (0.0 if med_vpd is None else np.log1p(med_vpd)) * 0.45
            + (0.0 if p90_vpd is None else np.log1p(p90_vpd)) * 0.25
            + (0.0 if med_viral is None else np.log1p(max(med_viral, 0))) * 0.15
            + trend * 0.15
        )
        viral_raw = (
            (med_eng or 0) * 0.35
            + (med_like or 0) * 0.20
            + (med_comment or 0) * 0.15
            + (0.0 if med_viral is None else min(med_viral / 1000.0, 1.0)) * 0.30
        )
        competition_raw = (
            np.log1p(density) * 0.35
            + mega_share * 0.25
            + min(n_videos / 200.0, 1.0) * 0.20
            + min(n_channels / 50.0, 1.0) * 0.20
        )

        age_rpm = {
            "2-5": 0.35,
            "6-8": 0.40,
            "9-12": 0.50,
            "13-17": 0.70,
            "18-24": 0.75,
        }.get(str(age), 0.5)
        brand_safety = 0.7 if str(theme) not in {"romance_crush", "absurd_surreal", "memes"} else 0.55
        monetization_raw = age_rpm * 0.4 + brand_safety * 0.2 + 0.2 + 0.2

        dialogue_rate = 0.5
        if "dialogue" in g:
            dialogue_rate = float(g["dialogue"].dropna().mean()) if g["dialogue"].notna().any() else 0.5
        music_rate = 0.5
        if "music" in g:
            music_rate = float(g["music"].dropna().mean()) if g["music"].notna().any() else 0.5
        complexity_raw = (
            dialogue_rate * 0.25
            + 0.5 * 0.25
            + (0.6 if character == "recurring_protagonist" else 0.3) * 0.20
            + music_rate * 0.15
            + (0.4 if "15_30" in str(fmt) or "under_15" in str(fmt) else 0.6) * 0.15
        )

        recurring_rate = float((g["character"] == "recurring_protagonist").mean())
        ip_raw = recurring_rate * 0.4 + 0.3 + 0.3
        loc_raw = (1.0 - dialogue_rate) * 0.35 + 0.25 + 0.25 + 0.15

        insufficient = (
            n_videos < int(gates.get("min_videos_per_niche", 30))
            or n_channels < int(gates.get("min_channels_per_niche", 5))
            or n_channels < int(gates.get("min_independent_channels_per_age_theme", 5))
            or max_ch_share > float(gates.get("max_channel_share_per_niche", 0.25))
            or unknown_rate > float(gates.get("max_unknown_rate", 0.35))
            or med_conf < float(gates.get("min_confidence_median", 0.55))
        )

        niches.append(
            NicheScore(
                niche=NicheKey(
                    age=str(age),
                    theme=str(theme),
                    format=str(fmt),
                    language=str(lang),
                    character=str(character),
                ),
                n_videos=n_videos,
                n_channels=n_channels,
                median_views_per_day=med_vpd,
                p90_views_per_day=p90_vpd,
                components=ComponentScores(
                    demand=float(demand_raw),
                    viral=float(viral_raw),
                    competition=float(competition_raw),
                    production_complexity=float(complexity_raw),
                    monetization=float(monetization_raw),
                    ip_potential=float(ip_raw),
                    localization=float(loc_raw),
                ),
                opportunity_score=None,
                confidence=med_conf,
                evidence_status=EvidenceKind.UNKNOWN if insufficient else EvidenceKind.INFERENCE,
                insufficient_data=insufficient,
                max_channel_share=max_ch_share,
                unknown_rate=unknown_rate,
                notes=[
                    "Opportunity metrics use POST_2025_03_31 Shorts (and NON_SHORT control); PRE epoch excluded.",
                    "Component scores are INFERENCE proxies, not FACT RPM.",
                    "madeForKids is FACT and is not used as estimated_target_age.",
                ],
            )
        )

    if not niches:
        return niches

    def extract(attr: str) -> pd.Series:
        return pd.Series([getattr(n.components, attr) for n in niches])

    demand_n = _minmax(extract("demand"))
    viral_n = _minmax(extract("viral"))
    comp_n = _minmax(extract("competition"))
    complex_n = _minmax(extract("production_complexity"))
    mon_n = _minmax(extract("monetization"))
    ip_n = _minmax(extract("ip_potential"))
    loc_n = _minmax(extract("localization"))

    for i, n in enumerate(niches):
        n.components = ComponentScores(
            demand=float(demand_n.iloc[i]),
            viral=float(viral_n.iloc[i]),
            competition=float(comp_n.iloc[i]),
            production_complexity=float(complex_n.iloc[i]),
            monetization=float(mon_n.iloc[i]),
            ip_potential=float(ip_n.iloc[i]),
            localization=float(loc_n.iloc[i]),
        )
        if n.insufficient_data and gates.get("declare_winner_requires_gates", True):
            n.opportunity_score = None
            n.evidence_status = EvidenceKind.UNKNOWN
            continue
        score = (
            n.components.demand * float(weights.get("demand", 0.22))
            + n.components.viral * float(weights.get("viral", 0.18))
            + (1.0 - n.components.competition) * float(weights.get("competition_inverse", 0.15))
            + n.components.monetization * float(weights.get("monetization", 0.18))
            + (1.0 - n.components.production_complexity)
            * float(weights.get("production_complexity_inverse", 0.08))
            + n.components.ip_potential * float(weights.get("ip_potential", 0.10))
            + n.components.localization * float(weights.get("localization", 0.09))
        )
        n.opportunity_score = float(score)
        n.evidence_status = EvidenceKind.INFERENCE

    return niches


def run_score(
    normalized: pd.DataFrame,
    classifications: list[dict[str, Any]],
    trends_by_theme: dict[str, float] | None = None,
) -> list[NicheScore]:
    paths = project_paths()
    df = build_analysis_frame(normalized, classifications)
    niches = score_niches(df, trends_by_theme=trends_by_theme)
    payload = [n.model_dump(mode="json") for n in niches]
    write_json(paths["scored"] / "niche_scores.json", payload)
    write_csv(paths["scored"] / "niche_scores.csv", payload)
    write_json(
        paths["scored"] / "scoring_meta.json",
        {
            "n_niches": len(niches),
            "n_scored": sum(1 for n in niches if n.opportunity_score is not None),
            "n_insufficient": sum(1 for n in niches if n.insufficient_data),
            "config": get_scoring_config(),
            "epistemic_note": (
                "Opportunity scores are INFERENCE. Do not treat as FACT commercial proof."
            ),
        },
    )
    return niches
