from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from cartoon_niche_radar.collectors.quota import QuotaExceededError, QuotaManager
from cartoon_niche_radar.collectors.query_scheduler import QueryScheduler
from cartoon_niche_radar.collectors.resume_state import CollectionState
from cartoon_niche_radar.models.evidence import Evidenced
from cartoon_niche_radar.models.schemas import MadeForKids, Platform, ShortOrLong, VideoRecord
from cartoon_niche_radar.utils.config import get_collection_config, get_settings, get_taxonomy, load_yaml
from cartoon_niche_radar.utils.epochs import classify_views_metric_epoch
from cartoon_niche_radar.utils.shorts import (
    classify_youtube_content_type,
    duration_bin,
)
from cartoon_niche_radar.utils.time import (
    age_days,
    channel_size_bucket,
    parse_iso8601_duration,
    safe_div,
    utcnow,
)


class YouTubeCollector:
    """Phase 1 primary collector — discovery ≠ enrichment, resume-safe, quota-aware."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        state: Optional[CollectionState] = None,
        quota: Optional[QuotaManager] = None,
        require_api_key: bool = True,
        scheduler: Optional[QueryScheduler] = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.youtube_api_key
        self.collection = get_collection_config()
        self.taxonomy = get_taxonomy()
        self.quota = quota or QuotaManager(load_yaml("quota.yaml"))
        self.state = state or CollectionState()
        self.scheduler = scheduler or QueryScheduler(self.collection, load_yaml("quota.yaml"))
        if self.state.data.get("quota_usage"):
            self.quota.load_spent(
                self.state.data.get("quota_usage") or {},
                self.state.data.get("quota_pt_date"),
            )
        self.youtube = None
        self.last_search_params: Optional[Dict[str, Any]] = None
        self.last_plan: Optional[Dict[str, Any]] = None
        if self.api_key:
            self.youtube = build("youtube", "v3", developerKey=self.api_key, cache_discovery=False)
        elif require_api_key:
            raise ValueError("YOUTUBE_API_KEY is required. Set it in .env (see .env.example).")

    # ------------------------------------------------------------------ seeds
    def build_core_seeds(self) -> List[Dict[str, str]]:
        """CORE discovery seeds — no numeric age labels in queries."""
        yt = self.collection.get("youtube", {})
        base = list(yt.get("base_queries", []))
        themes = list(yt.get("core_theme_queries") or self.taxonomy.get("themes", []))
        themes = [t for t in themes if t != "other"]
        seeds: List[Dict[str, str]] = []
        for b in base:
            for theme in themes:
                theme_label = theme.replace("_", " ")
                seeds.append(
                    {
                        "query": f"{b} {theme_label}",
                        "seed_id": f"CORE|{b}|{theme}",
                        "theme": theme,
                        "target_age_hypothesis": "UNKNOWN",
                        "sample_role": "CORE",
                        "source_seed_family": f"core:{theme}",
                    }
                )
        if self.collection.get("stratified_discovery", {}).get("round_robin_seeds", True):
            seeds = self._round_robin_by_theme(seeds)
        return seeds

    def build_coverage_seeds(self) -> List[Dict[str, str]]:
        """COVERAGE recall seeds — optional; tagged sample_role=COVERAGE."""
        if not self.collection.get("youtube", {}).get("coverage_enabled", True):
            return []
        out: List[Dict[str, str]] = []
        for row in self.collection.get("youtube", {}).get("coverage_queries", []):
            out.append(
                {
                    "query": row["query"],
                    "seed_id": f"COVERAGE|{row.get('source_seed_family', row['query'])}",
                    "theme": "animation",
                    "target_age_hypothesis": row.get("age_hypothesis", "UNKNOWN"),
                    "sample_role": "COVERAGE",
                    "source_seed_family": row.get("source_seed_family", row["query"]),
                }
            )
        return out

    def build_stratified_seeds(self) -> List[Dict[str, str]]:
        """All seeds for planning (CORE first, then COVERAGE)."""
        return self.build_core_seeds() + self.build_coverage_seeds()

    @staticmethod
    def _round_robin_by_theme(seeds: List[Dict[str, str]]) -> List[Dict[str, str]]:
        by_theme: Dict[str, List[Dict[str, str]]] = {}
        for s in seeds:
            by_theme.setdefault(s["theme"], []).append(s)
        ordered: List[Dict[str, str]] = []
        keys = list(by_theme.keys())
        idx = 0
        while any(by_theme.values()):
            t = keys[idx % len(keys)]
            if by_theme[t]:
                ordered.append(by_theme[t].pop(0))
            idx += 1
            if idx > len(seeds) * 3:
                break
        return ordered

    # ------------------------------------------------------------------ API helpers
    def _execute(self, endpoint: str, params: Dict[str, Any], request) -> Dict[str, Any]:
        self.quota.check_or_raise(endpoint)
        try:
            resp = request.execute()
            self.quota.charge(endpoint, params, success=True)
            return resp
        except Exception as exc:  # noqa: BLE001
            self.quota.charge(endpoint, params, success=False, error=str(exc))
            raise

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=20),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(HttpError),
        reraise=True,
    )
    def _search_page(
        self,
        query: str,
        *,
        order: str,
        region_code: Optional[str],
        relevance_language: Optional[str],
        page_token: Optional[str],
        max_results: int,
        published_after: Optional[str] = None,
    ) -> Dict[str, Any]:
        assert self.youtube is not None
        params: Dict[str, Any] = {
            "q": query,
            "order": order,
            "regionCode": region_code,
            "relevanceLanguage": relevance_language,
            "pageToken": page_token,
            "maxResults": max_results,
            "type": "video",
            "publishedAfter": published_after,
            "videoDuration": self.collection.get("youtube", {})
            .get("shorts_filters", {})
            .get("video_duration_api", "short"),
        }
        self.last_search_params = dict(params)
        kwargs = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": order,
            "maxResults": max_results,
            "pageToken": page_token,
            "videoDuration": params["videoDuration"],
            "regionCode": region_code,
            "relevanceLanguage": relevance_language,
        }
        if published_after and self.collection.get("youtube", {}).get("search", {}).get(
            "apply_published_after", True
        ):
            kwargs["publishedAfter"] = published_after
        req = self.youtube.search().list(**kwargs)
        return self._execute("search.list", params, req)

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=20),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(HttpError),
        reraise=True,
    )
    def _videos_list(self, ids: List[str], part: str = "snippet,contentDetails,status") -> Dict[str, Any]:
        assert self.youtube is not None
        params = {"id": ",".join(ids), "part": part}
        req = self.youtube.videos().list(part=part, id=",".join(ids))
        return self._execute("videos.list", params, req)

    def _batch_get_stats(self, ids: List[str]) -> Dict[str, Any]:
        assert self.youtube is not None
        params = {"id": ",".join(ids), "part": "statistics,contentDetails,snippet"}
        videos_resource = self.youtube.videos()
        if hasattr(videos_resource, "batchGetStats"):
            req = videos_resource.batchGetStats(
                id=",".join(ids), part="statistics,contentDetails,snippet"
            )
            return self._execute("videos.batchGetStats", params, req)
        from googleapiclient.http import HttpRequest

        uri = (
            "https://www.googleapis.com/youtube/v3/videos:batchGetStats"
            f"?part=statistics%2CcontentDetails%2Csnippet&id={','.join(ids)}"
            f"&key={self.api_key}"
        )
        req = HttpRequest(self.youtube._http, self.youtube._postproc, uri, method="GET")  # noqa: SLF001
        return self._execute("videos.batchGetStats", params, req)

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=20),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(HttpError),
        reraise=True,
    )
    def _channels_list(self, ids: List[str], part: str = "snippet,statistics,contentDetails") -> Dict[str, Any]:
        assert self.youtube is not None
        params = {"id": ",".join(ids), "part": part}
        req = self.youtube.channels().list(part=part, id=",".join(ids))
        return self._execute("channels.list", params, req)

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=20),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(HttpError),
        reraise=True,
    )
    def _playlist_items(
        self, playlist_id: str, *, page_token: Optional[str], max_results: int
    ) -> Dict[str, Any]:
        assert self.youtube is not None
        params = {"playlistId": playlist_id, "pageToken": page_token, "maxResults": max_results}
        req = self.youtube.playlistItems().list(
            part="contentDetails,snippet",
            playlistId=playlist_id,
            maxResults=max_results,
            pageToken=page_token,
        )
        return self._execute("playlistItems.list", params, req)

    # ------------------------------------------------------------------ caps
    def _soft_relevant(self, title: str, description: str) -> bool:
        text = f"{title} {description}".lower()
        rel = self.collection.get("relevance", {})
        for bad in rel.get("reject_tokens", []):
            if bad.lower() in text:
                return False
        tokens = rel.get("require_any_tokens", [])
        if not tokens:
            return True
        return any(t.lower() in text for t in tokens)

    def _within_strata_caps(self, seed: Dict[str, str], channel_id: Optional[str] = None) -> bool:
        """Caps use persisted discovered count (IDs are accepted immediately)."""
        strat = self.collection.get("stratified_discovery", {})
        if not strat.get("enabled", True):
            return True
        total = max(1, self.state.effective_discovered_count())
        theme = seed.get("theme")
        seed_id = seed.get("seed_id")
        role = seed.get("sample_role", "CORE")
        if theme and self.state.stratum_share(f"theme:{theme}", total) > float(
            strat.get("max_share_per_theme", 0.12)
        ):
            return False
        if seed_id and self.state.stratum_share(f"seed:{seed_id}", total) > float(
            strat.get("max_share_per_seed", 0.08)
        ):
            return False
        # Age-hypothesis share only for COVERAGE
        age_h = seed.get("target_age_hypothesis")
        if role == "COVERAGE" and age_h and age_h != "UNKNOWN":
            if self.state.stratum_share(f"age:{age_h}", total) > float(
                strat.get("max_share_per_age_hypothesis_coverage", 0.35)
            ):
                return False
        if channel_id:
            ch_cfg = self.collection.get("youtube", {}).get("channel_expansion", {})
            max_share = float(ch_cfg.get("max_share_per_channel", 0.05))
            if self.state.channel_share(channel_id, total) >= max_share:
                return False
            max_per = int(ch_cfg.get("max_videos_per_channel", 40))
            if int((self.state.data.get("channel_video_counts") or {}).get(channel_id, 0)) >= max_per:
                return False
        return True

    def _accept_id(
        self,
        video_id: str,
        *,
        seed: Dict[str, str],
        channel_id: Optional[str],
    ) -> bool:
        return self.state.accept_discovered(
            video_id,
            channel_id=channel_id,
            theme=seed.get("theme"),
            age_hypothesis=seed.get("target_age_hypothesis"),
            seed_id=seed.get("seed_id"),
            sample_role=seed.get("sample_role", "CORE"),
            source_seed_family=seed.get("source_seed_family"),
            persist=True,
        )

    # ------------------------------------------------------------------ discovery
    def discover_video_ids(self, max_new: int) -> List[str]:
        """DISCOVERY only — scheduled search + channel expansion. Does not enrich stats."""
        if self.youtube is None:
            raise ValueError("API key required for discovery")

        before = set(self.state.discovered())
        seeds = self.build_stratified_seeds()
        # Split SEARCH budget: majority CORE, optional COVERAGE share
        cov_share = float(self.collection.get("youtube", {}).get("coverage_search_budget_share", 0.15))
        plan = self.scheduler.load_or_build(seeds, pt_quota_date=self.quota.pt_quota_date())
        self.last_plan = plan

        # Prefer executing CORE slots first within remaining budget
        slots = list(plan.get("slots") or [])
        completed = set(plan.get("completed_query_keys") or [])
        slots = [s for s in slots if s.get("query_key") not in completed]
        core_slots = [s for s in slots if s.get("sample_role") == "CORE"]
        cov_slots = [s for s in slots if s.get("sample_role") == "COVERAGE"]
        # Rebalance remaining slots by configured coverage share
        remaining_budget = max(0, int(plan.get("planned_search_calls", 0)) - int(plan.get("executed_search_calls", 0)))
        n_cov = min(len(cov_slots), int(remaining_budget * cov_share))
        ordered_slots = core_slots + cov_slots[:n_cov]

        channel_candidates: Set[str] = set()
        accepted_this_run = 0
        yt = self.collection.get("youtube", {})
        page_size = min(50, int(yt.get("search", {}).get("results_per_page", 50)))

        for slot in ordered_slots:
            if accepted_this_run >= max_new or not self.quota.can_afford("search.list"):
                break
            seed = {
                "seed_id": slot["seed_id"],
                "query": slot["query"],
                "theme": slot.get("theme", "other"),
                "target_age_hypothesis": "UNKNOWN"
                if slot.get("sample_role") == "CORE"
                else next(
                    (
                        s.get("target_age_hypothesis", "UNKNOWN")
                        for s in seeds
                        if s["seed_id"] == slot["seed_id"]
                    ),
                    "UNKNOWN",
                ),
                "sample_role": slot.get("sample_role", "CORE"),
                "source_seed_family": slot.get("source_seed_family"),
            }
            if not self._within_strata_caps(seed):
                continue
            query_key = slot["query_key"]
            if self.state.is_query_done(query_key):
                self.scheduler.mark_executed(plan, query_key, success=True)
                continue
            token = self.state.get_page_token(query_key)
            max_pages = int(slot.get("max_pages") or 1)
            pages = 0
            while pages < max_pages and self.quota.can_afford("search.list"):
                try:
                    resp = self._search_page(
                        seed["query"],
                        order=slot["order"],
                        region_code=slot["region"],
                        relevance_language=slot["language"],
                        page_token=token,
                        max_results=page_size,
                        published_after=slot.get("publishedAfter") or plan.get("publishedAfter"),
                    )
                except QuotaExceededError:
                    self._persist()
                    return sorted(self.state.discovered() - before)
                except HttpError:
                    self.scheduler.mark_executed(plan, query_key, success=False)
                    break

                for item in resp.get("items", []):
                    if accepted_this_run >= max_new:
                        break
                    vid = (item.get("id") or {}).get("videoId")
                    snip = item.get("snippet") or {}
                    ch = snip.get("channelId")
                    if not vid or vid in self.state.discovered():
                        continue
                    if not self._soft_relevant(snip.get("title", ""), snip.get("description", "")):
                        continue
                    if not self._within_strata_caps(seed, ch):
                        continue
                    # Persist ID BEFORE page-progress update
                    if self._accept_id(vid, seed=seed, channel_id=ch):
                        accepted_this_run += 1
                        if ch:
                            channel_candidates.add(ch)

                token = resp.get("nextPageToken")
                # Page progress only after IDs from this page are persisted
                self.state.set_page_token(query_key, token)
                self.state.note_collection_date()
                self._persist()
                pages += 1
                self.scheduler.mark_executed(plan, query_key, success=True)
                if not token:
                    self.state.mark_query_done(query_key)
                    break
            if not self.state.get_page_token(query_key):
                self.state.mark_query_done(query_key)
            self._persist()

        if (
            yt.get("channel_expansion", {}).get("enabled", True)
            and accepted_this_run < max_new
            and self.quota.can_afford("channels.list")
        ):
            self._expand_channels(sorted(channel_candidates), max_new - accepted_this_run)

        self.state.note_collection_date()
        self._persist()
        self.last_plan = self.scheduler.load_plan() or plan
        return sorted(self.state.discovered() - before)

    def _expand_channels(self, channel_ids: List[str], max_new: int) -> List[str]:
        out: List[str] = []
        if not channel_ids or max_new <= 0:
            return out
        exp = self.collection.get("youtube", {}).get("channel_expansion", {})
        max_per = int(exp.get("max_videos_per_channel", 40))
        page_size = int(exp.get("playlist_page_size", 50))
        max_pages = int(exp.get("max_playlist_pages_per_channel", 2))
        max_new_channels = int(
            self.collection.get("youtube", {}).get("discovery", {}).get("max_new_channels_per_day", 40)
        )
        processed = 0
        seed = {
            "theme": "animation",
            "target_age_hypothesis": "UNKNOWN",
            "seed_id": "channel_exp",
            "sample_role": "CORE",
            "source_seed_family": "channel_expansion",
        }

        for i in range(0, len(channel_ids), 50):
            if len(out) >= max_new or processed >= max_new_channels:
                break
            batch = [c for c in channel_ids[i : i + 50] if not self.state.is_channel_done(c)]
            if not batch or not self.quota.can_afford("channels.list"):
                break
            try:
                cresp = self._channels_list(batch)
            except QuotaExceededError:
                break
            for ch in cresp.get("items", []):
                if len(out) >= max_new or processed >= max_new_channels:
                    break
                cid = ch["id"]
                uploads = (
                    (ch.get("contentDetails") or {}).get("relatedPlaylists", {}).get("uploads")
                )
                if not uploads:
                    self.state.mark_channel_done(cid)
                    continue
                token = None
                pages = 0
                taken = 0
                while (
                    pages < max_pages
                    and taken < max_per
                    and len(out) < max_new
                    and self.quota.can_afford("playlistItems.list")
                ):
                    try:
                        presp = self._playlist_items(uploads, page_token=token, max_results=page_size)
                    except QuotaExceededError:
                        self._persist()
                        return out
                    for item in presp.get("items", []):
                        vid = (item.get("contentDetails") or {}).get("videoId")
                        if not vid or vid in self.state.discovered():
                            continue
                        if not self._within_strata_caps(seed, cid):
                            continue
                        snip = item.get("snippet") or {}
                        if not self._soft_relevant(snip.get("title", ""), snip.get("description", "")):
                            continue
                        if self._accept_id(vid, seed=seed, channel_id=cid):
                            out.append(vid)
                            taken += 1
                        if taken >= max_per or len(out) >= max_new:
                            break
                    token = presp.get("nextPageToken")
                    pages += 1
                    self._persist()
                    if not token:
                        break
                self.state.mark_channel_done(cid)
                processed += 1
                self._persist()
        return out

    # ------------------------------------------------------------------ enrichment
    def enrich_video_ids(self, video_ids: Optional[List[str]] = None) -> List[VideoRecord]:
        if self.youtube is None:
            raise ValueError("API key required for enrichment")
        ids = video_ids if video_ids is not None else self.state.pending_enrichment()
        ids = [i for i in ids if i not in self.state.enriched()]
        if not ids:
            return []

        enrich_cfg = self.collection.get("youtube", {}).get("enrichment", {})
        prefer_batch = bool(enrich_cfg.get("prefer_batch_get_stats", True))
        batch_stats = int(enrich_cfg.get("batch_get_stats_size", 50))
        batch_list = int(enrich_cfg.get("batch_videos_list_size", 50))
        always_status = bool(enrich_cfg.get("always_fetch_status_via_videos_list", True))

        stats_by_id: Dict[str, Dict[str, Any]] = {}
        meta_by_id: Dict[str, Dict[str, Any]] = {}

        if prefer_batch:
            for i in range(0, len(ids), batch_stats):
                batch = ids[i : i + batch_stats]
                if not self.quota.can_afford("videos.batchGetStats"):
                    break
                try:
                    resp = self._batch_get_stats(batch)
                except QuotaExceededError:
                    break
                except Exception:
                    prefer_batch = False
                    break
                for item in resp.get("items", []):
                    stats_by_id[item.get("id")] = item

        need_list = ids if always_status or not prefer_batch else [i for i in ids if i not in stats_by_id]
        for i in range(0, len(need_list), batch_list):
            batch = need_list[i : i + batch_list]
            if not self.quota.can_afford("videos.list"):
                break
            try:
                resp = self._videos_list(batch, part="snippet,contentDetails,status,statistics")
            except QuotaExceededError:
                break
            for item in resp.get("items", []):
                meta_by_id[item["id"]] = item
                if item["id"] not in stats_by_id:
                    stats_by_id[item["id"]] = item

        channel_ids = sorted(
            {
                (meta_by_id.get(vid) or stats_by_id.get(vid) or {}).get("snippet", {}).get("channelId")
                for vid in ids
                if (meta_by_id.get(vid) or stats_by_id.get(vid))
            }
            - {None, ""}
        )
        channel_cache: Dict[str, Dict[str, Any]] = {}
        for i in range(0, len(channel_ids), 50):
            batch = channel_ids[i : i + 50]
            if not self.quota.can_afford("channels.list"):
                break
            try:
                cresp = self._channels_list(batch, part="snippet,statistics")
            except QuotaExceededError:
                break
            for ch in cresp.get("items", []):
                channel_cache[ch["id"]] = ch

        max_collect = int(self.collection.get("target", {}).get("max_duration_seconds_collect", 180))
        records: List[VideoRecord] = []
        enriched_ids: List[str] = []
        video_meta = self.state.data.get("video_meta") or {}
        for vid in ids:
            item = meta_by_id.get(vid) or stats_by_id.get(vid)
            if not item:
                continue
            if vid in stats_by_id and vid in meta_by_id:
                merged = dict(meta_by_id[vid])
                if "statistics" in stats_by_id[vid]:
                    merged["statistics"] = stats_by_id[vid]["statistics"]
                item = merged
            ch = channel_cache.get((item.get("snippet") or {}).get("channelId"))
            rec = self._to_record(item, ch, max_collect, discovery_meta=video_meta.get(vid) or {})
            if rec is not None:
                records.append(rec)
                enriched_ids.append(vid)

        self.state.add_enriched(enriched_ids)
        self._persist()
        return records

    def _to_record(
        self,
        item: Dict[str, Any],
        channel: Optional[Dict[str, Any]],
        max_collect: int,
        discovery_meta: Optional[Dict[str, Any]] = None,
    ) -> Optional[VideoRecord]:
        snip = item.get("snippet", {})
        stats = item.get("statistics", {})
        details = item.get("contentDetails", {})
        status = item.get("status", {})
        discovery_meta = discovery_meta or {}

        duration = parse_iso8601_duration(details.get("duration"))
        if duration is None and details.get("durationMillis") is not None:
            try:
                duration = int(int(details["durationMillis"]) / 1000)
            except (TypeError, ValueError):
                duration = None

        publish_raw = snip.get("publishedAt") or snip.get("publishTime")
        publish_date = (
            datetime.fromisoformat(publish_raw.replace("Z", "+00:00")) if publish_raw else None
        )
        views = int(stats["viewCount"]) if "viewCount" in stats else None
        likes = int(stats["likeCount"]) if "likeCount" in stats else None
        comments = int(stats["commentCount"]) if "commentCount" in stats else None
        days = age_days(publish_date)
        vpd = safe_div(views, days)

        ch_stats = (channel or {}).get("statistics", {})
        subs = int(ch_stats["subscriberCount"]) if "subscriberCount" in ch_stats else None
        vcount = int(ch_stats["videoCount"]) if "videoCount" in ch_stats else None
        country = (channel or {}).get("snippet", {}).get("country")
        language = snip.get("defaultAudioLanguage") or snip.get("defaultLanguage")

        if duration is not None and duration > max_collect:
            # Still store as NON_SHORT if slightly over? Drop > collect max for first pass.
            return None

        ctype, ctype_conf, ctype_source, ctype_feats = classify_youtube_content_type(
            duration_seconds=duration,
            publish_date=publish_date,
            search_video_duration_filter=self.collection.get("youtube", {})
            .get("shorts_filters", {})
            .get("video_duration_api"),
        )
        epoch = classify_views_metric_epoch(
            publish_date=publish_date,
            youtube_content_type=ctype.value,
            content_type_confidence=ctype_conf,
            min_inferred_confidence=float(
                self.collection.get("shorts_views_metric_break", {}).get("min_inferred_confidence", 0.7)
            ),
        )

        # Legacy short_or_long kept for compatibility — NOT Shorts confirmation
        if duration is None:
            short_or_long = ShortOrLong.UNKNOWN
        elif duration <= 180:
            short_or_long = ShortOrLong.SHORT  # means short-form duration band, not Shorts
        else:
            short_or_long = ShortOrLong.LONG

        mfk_raw = status.get("madeForKids")
        if mfk_raw is True:
            made_for_kids = MadeForKids.TRUE
        elif mfk_raw is False:
            made_for_kids = MadeForKids.FALSE
        else:
            made_for_kids = MadeForKids.UNKNOWN

        evidence = {
            "views": Evidenced.fact(views, "youtube.videos.statistics").as_dict(),
            "duration_seconds": Evidenced.fact(duration, "youtube.videos.contentDetails").as_dict(),
            "made_for_kids": (
                Evidenced.fact(made_for_kids.value, "YOUTUBE_API").as_dict()
                if made_for_kids != MadeForKids.UNKNOWN
                else Evidenced.unknown("status.madeForKids not present").as_dict()
            ),
            "youtube_content_type": {
                "value": ctype.value,
                "confidence": ctype_conf,
                "source": ctype_source,
                "evidence_features": ctype_feats,
                "kind": "INFERENCE",
            },
            "views_metric_epoch": Evidenced.fact(epoch.value, "shorts_views_break_rule").as_dict(),
            "estimated_target_age": Evidenced.unknown(
                "INFERENCE in Phase 4 — never derived solely from madeForKids"
            ).as_dict(),
            "search_videoDuration_short_is_not_shorts_confirmation": Evidenced.fact(
                True, "youtube_api_docs"
            ).as_dict(),
        }

        return VideoRecord(
            video_id=item["id"],
            channel_id=snip.get("channelId", ""),
            platform=Platform.YOUTUBE,
            title=snip.get("title"),
            description=snip.get("description"),
            publish_date=publish_date,
            duration_seconds=duration,
            duration_bin=duration_bin(duration).value,
            views=views,
            likes=likes,
            comments=comments,
            views_per_day=vpd,
            channel_subscribers=subs,
            video_count=vcount,
            language=language,
            country=country,
            short_or_long=short_or_long,
            youtube_content_type=ctype.value,
            youtube_content_type_confidence=ctype_conf,
            made_for_kids=made_for_kids,
            views_metric_epoch=epoch.value,
            channel_size_bucket=channel_size_bucket(subs),
            sample_role=discovery_meta.get("sample_role", "CORE"),
            source_seed_family=discovery_meta.get("source_seed_family"),
            field_evidence=evidence,
            collected_at=utcnow(),
            source="youtube_data_api_v3",
        )

    def _persist(self) -> None:
        self.state.set_quota_usage(self.quota.snapshot())
        self.state.save()

    def collect(self, max_videos: int = 500) -> List[VideoRecord]:
        need = max(0, max_videos - len(self.state.enriched()))
        if need > 0:
            pending = self.state.pending_enrichment()
            if len(pending) < need:
                self.discover_video_ids(need - len(pending))
        return self.enrich_video_ids()
