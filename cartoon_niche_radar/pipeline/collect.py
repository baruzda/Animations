from __future__ import annotations

from rich.console import Console

from cartoon_niche_radar.collectors.instagram import InstagramCollector
from cartoon_niche_radar.collectors.quota import QuotaExceededError
from cartoon_niche_radar.collectors.resume_state import CollectionState
from cartoon_niche_radar.collectors.tiktok import TikTokCollector
from cartoon_niche_radar.collectors.trends import GoogleTrendsSignal
from cartoon_niche_radar.collectors.youtube import YouTubeCollector
from cartoon_niche_radar.pipeline.stages import get_stage, write_stage_qa
from cartoon_niche_radar.storage.database import init_db, upsert_videos
from cartoon_niche_radar.storage.export import write_json, write_jsonl
from cartoon_niche_radar.utils.config import get_collection_config, project_paths
from cartoon_niche_radar.utils.time import utcnow

console = Console()


def run_collect(
    *,
    max_videos: int | None = None,
    dry_run: bool = False,
    stage: str | None = None,
    discover_only: bool = False,
    enrich_only: bool = False,
) -> dict:
    paths = project_paths()
    paths["raw"].mkdir(parents=True, exist_ok=True)
    target = get_collection_config().get("target", {})

    if stage:
        stage_cfg = get_stage(stage)
        goal = int(stage_cfg["target_videos"])
    else:
        goal = max_videos or int(target.get("min_relevant_videos", 10000))
        stage_cfg = None

    meta: dict = {
        "phase": 1,
        "started_at": utcnow().isoformat(),
        "target_videos": goal,
        "stage": stage_cfg["id"] if stage_cfg else None,
        "mode": "enrich_only" if enrich_only else ("discover_only" if discover_only else "full"),
        "sources": {},
        "fact_inference_unknown": {
            "FACT": [
                "YouTube Data API v3 is the primary source.",
                "TikTok Research API prohibits commercial use under current ToS.",
                "YouTube Shorts view counting methodology changed on 2025-03-31.",
                "June 2026: search.list and videos.batchGetStats use separate quota buckets.",
            ],
            "INFERENCE": [],
            "UNKNOWN": [],
        },
    }

    tiktok = TikTokCollector().collect()
    ig = InstagramCollector().collect_hashtag("aicartoon")
    meta["sources"]["tiktok"] = tiktok
    meta["sources"]["instagram"] = ig
    if tiktok.get("kind") == "UNKNOWN":
        meta["fact_inference_unknown"]["UNKNOWN"].append(tiktok.get("reason"))
    if ig.get("kind") == "UNKNOWN":
        meta["fact_inference_unknown"]["UNKNOWN"].append(ig.get("reason"))

    trends = GoogleTrendsSignal().interest_over_time(
        ["AI cartoon", "animated shorts", "cartoon shorts", "AI animation"]
    )
    meta["sources"]["google_trends"] = {
        "status": trends.get("status"),
        "kind": trends.get("kind"),
        "keywords": list((trends.get("series") or {}).keys()),
    }
    write_json(paths["raw"] / "google_trends.json", trends)

    if dry_run:
        meta["status"] = "dry_run"
        meta["note"] = "Dry run: no YouTube API calls executed."
        meta["fact_inference_unknown"]["UNKNOWN"].append(
            "Video performance metrics unknown until live collection."
        )
        meta["staged_protocol"] = get_collection_config().get("stages")
        write_json(paths["raw"] / "collect_meta.json", meta)
        if stage_cfg:
            write_stage_qa(stage_cfg["id"], sample_size=0, gates_passed=False, extra={"dry_run": True})
        return meta

    state = CollectionState()
    if stage_cfg:
        state.data["stage"] = stage_cfg["id"]
        state.save()

    collector = YouTubeCollector(state=state, require_api_key=True)
    records = []
    try:
        if discover_only:
            console.print(f"[bold]DISCOVERY only — up to {goal} new IDs…[/bold]")
            new_ids = collector.discover_video_ids(goal)
            meta["discovered_new"] = len(new_ids)
            meta["discovered_total"] = len(state.discovered())
        elif enrich_only:
            console.print("[bold]ENRICHMENT only — pending discovered IDs…[/bold]")
            records = collector.enrich_video_ids()
        else:
            console.print(f"[bold]Collect (discover→enrich) toward {goal}…[/bold]")
            # Multi-day: goal is cumulative enriched count
            need = max(0, goal - len(state.enriched()))
            if need > 0 and len(state.pending_enrichment()) < need:
                collector.discover_video_ids(need - len(state.pending_enrichment()))
            records = collector.enrich_video_ids()
    except QuotaExceededError as exc:
        meta["status"] = "stopped_before_quota_exceed"
        meta["quota_stop"] = str(exc)
        records = collector.enrich_video_ids()  # enrich whatever already discovered if affordable
        meta["fact_inference_unknown"]["FACT"].append(
            "Collector stopped before exceeding configured quota buckets."
        )

    meta["quota"] = collector.quota.snapshot()
    meta["resume"] = {
        "discovered": len(state.discovered()),
        "enriched": len(state.enriched()),
        "pending_enrichment": len(state.pending_enrichment()),
        "completed_queries": len(state.data.get("completed_queries") or []),
        "completed_channels": len(state.data.get("completed_channels") or []),
        "collection_dates": state.data.get("collection_dates"),
    }

    if records:
        Session = init_db()
        with Session() as session:
            upsert_videos(session, records)
        # Append-safe merge into jsonl: rewrite from all enriched records in this run only
        # Full cumulative export left to DB; this file holds latest enrichment batch + prior if present
        write_jsonl(
            paths["raw"] / "youtube_videos.jsonl",
            [r.model_dump(mode="json") for r in records],
        )

    meta["status"] = meta.get("status") or "ok"
    meta["collected_this_run"] = len(records)
    meta["finished_at"] = utcnow().isoformat()
    if len(state.enriched()) < goal:
        meta["fact_inference_unknown"]["UNKNOWN"].append(
            f"Enriched {len(state.enriched())} < target {goal}; resume another PT-day."
        )
    write_json(paths["raw"] / "collect_meta.json", meta)

    if stage_cfg:
        write_stage_qa(
            stage_cfg["id"],
            sample_size=len(state.enriched()),
            gates_passed=False,
            extra={"resume": meta["resume"], "quota": meta["quota"]},
        )
    return meta
