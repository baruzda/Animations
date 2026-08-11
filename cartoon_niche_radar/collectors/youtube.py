from __future__ import annotations

import itertools
from datetime import date, datetime
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from cartoon_niche_radar.collectors.quota import QuotaExceededError, QuotaManager
from cartoon_niche_radar.collectors.resume_state import CollectionState
from cartoon_niche_radar.models.evidence import Evidenced
from cartoon_niche_radar.models.schemas import MadeForKids, Platform, ShortOrLong, VideoRecord
from cartoon_niche_radar.utils.config import get_collection_config, get_settings, get_taxonomy, load_yaml
from cartoon_niche_radar.utils.epochs import classify_views_metric_epoch
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
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.youtube_api_key
        self.collection = get_collection_config()
        self.taxonomy = get_taxonomy()
        self.quota = quota or QuotaManager(load_yaml("quota.yaml"))
        self.state = state or CollectionState()
        if self.state.data.get("quota_usage"):
            self.quota.load_spent(
                self.state.data.get("quota_usage") or {},
                self.state.data.get("quota_pt_date"),
            )
        self.youtube = None
        if self.api_key:
            self.youtube = build("youtube", "v3", developerKey=self.api_key, cache_discovery=False)
        elif require_api_key:
            raise ValueError("YOUTUBE_API_KEY is required. Set it in .env (see .env.example).")

    # ------------------------------------------------------------------ seeds
    def build_stratified_seeds(self) -> List[Dict[str, str]]:
        """Build discovery seeds labeled by age-hypothesis × theme (stratified)."""
        base = list(self.collection.get("youtube", {}).get("base_queries", []))
        themes = list(self.taxonomy.get("themes", []))
        ages = self.taxonomy.get("age_clusters", [])
        seeds: List[Dict[str, str]] = []
        for b, theme, age in itertools.product(base, themes, ages):
            age_id = age.get("id", "UNKNOWN")
            age_label = age.get("label", age_id)
            theme_label = theme.replace("_", " ")
            q = f"{b} {theme_label} {age_label}"
            seeds.append(
                {
                    "query": q,
                    "seed_id": f"{b}|{theme}|{age_id}",
                    "theme": theme,
                    "target_age_hypothesis": age_id,
                }
            )
        # Round-robin across themes to avoid early-seed domination
        if self.collection.get("stratified_discovery", {}).get("round_robin_seeds", True):
            by_theme: Dict[str, List[Dict[str, str]]] = {}
            for s in seeds:
                by_theme.setdefault(s["theme"], []).append(s)
            ordered: List[Dict[str, str]] = []
            theme_keys = list(by_theme.keys())
            idx = 0
            while any(by_theme.values()):
                t = theme_keys[idx % len(theme_keys)]
                if by_theme[t]:
                    ordered.append(by_theme[t].pop(0))
                idx += 1
                if idx > len(seeds) * 2:
                    break
            seeds = ordered
        return seeds

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
    ) -> Dict[str, Any]:
        assert self.youtube is not None
        params = {
            "q": query,
            "order": order,
            "regionCode": region_code,
            "relevanceLanguage": relevance_language,
            "pageToken": page_token,
            "maxResults": max_results,
            "type": "video",
        }
        req = self.youtube.search().list(
            part="snippet",
            q=query,
            type="video",
            order=order,
            maxResults=max_results,
            pageToken=page_token,
            videoDuration=self.collection.get("youtube", {})
            .get("shorts_filters", {})
            .get("video_duration_api", "short"),
            regionCode=region_code,
            relevanceLanguage=relevance_language,
        )
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
        """Prefer official videos.batchGetStats (BATCH_STATS bucket)."""
        assert self.youtube is not None
        params = {
            "id": ",".join(ids),
            "part": "statistics,contentDetails,snippet",
        }
        # google-api-python-client may or may not expose batchGetStats depending on discovery doc.
        videos_resource = self.youtube.videos()
        if hasattr(videos_resource, "batchGetStats"):
            req = videos_resource.batchGetStats(
                id=",".join(ids),
                part="statistics,contentDetails,snippet",
            )
            return self._execute("videos.batchGetStats", params, req)
        # Fallback: HTTP discovery via custom request if method missing in client stubs.
        # Do not invent undocumented behavior beyond calling the known REST path.
        http = self.youtube._http  # noqa: SLF001 — client transport
        from googleapiclient.http import HttpRequest

        uri = (
            "https://www.googleapis.com/youtube/v3/videos:batchGetStats"
            f"?part=statistics%2CcontentDetails%2Csnippet&id={','.join(ids)}"
            f"&key={self.api_key}"
        )
        req = HttpRequest(http, self.youtube._postproc, uri, method="GET")  # noqa: SLF001
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
        params = {
            "playlistId": playlist_id,
            "pageToken": page_token,
            "maxResults": max_results,
        }
        req = self.youtube.playlistItems().list(
            part="contentDetails,snippet",
            playlistId=playlist_id,
            maxResults=max_results,
            pageToken=page_token,
        )
        return self._execute("playlistItems.list", params, req)

    # ------------------------------------------------------------------ discovery
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
        strat = self.collection.get("stratified_discovery", {})
        if not strat.get("enabled", True):
            return True
        total = max(1, len(self.state.discovered()))
        counts = self.state.data.get("strata_counts") or {}
        theme_key = f"theme:{seed['theme']}"
        age_key = f"age:{seed['target_age_hypothesis']}"
        seed_key = f"seed:{seed['seed_id']}"
        if counts.get(theme_key, 0) / total > float(strat.get("max_share_per_theme", 0.12)):
            return False
        if counts.get(age_key, 0) / total > float(strat.get("max_share_per_age_hypothesis", 0.30)):
            return False
        if counts.get(seed_key, 0) / total > float(strat.get("max_share_per_seed", 0.08)):
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

    def discover_video_ids(self, max_new: int) -> List[str]:
        """DISCOVERY only — search + channel expansion. Does not enrich stats."""
        if self.youtube is None:
            raise ValueError("API key required for discovery")
        yt = self.collection.get("youtube", {})
        search_cfg = yt.get("search", {})
        discovery_cfg = yt.get("discovery", {})
        orders = search_cfg.get("order_modes", ["date", "relevance"])
        regions = search_cfg.get("region_codes", ["US"])[:3]
        langs = search_cfg.get("relevance_languages", ["en"])[:2]
        max_pages = int(search_cfg.get("max_pages_per_query", 2))
        page_size = min(50, int(search_cfg.get("results_per_page", 50)))
        max_seeds = int(discovery_cfg.get("max_search_seeds_per_day", 80))

        seeds = self.build_stratified_seeds()
        new_ids: List[str] = []
        channel_candidates: Set[str] = set()
        seeds_used = 0

        for seed in seeds:
            if len(new_ids) >= max_new or seeds_used >= max_seeds:
                break
            if self.state.is_seed_done(seed["seed_id"]):
                continue
            if not self.quota.can_afford("search.list"):
                break
            if not self._within_strata_caps(seed):
                continue

            for order, region, lang in itertools.product(orders[:2], regions, langs):
                if len(new_ids) >= max_new or not self.quota.can_afford("search.list"):
                    break
                query_key = f"{seed['seed_id']}|{order}|{region}|{lang}"
                if self.state.is_query_done(query_key):
                    continue
                token = self.state.get_page_token(query_key)
                pages = 0
                while pages < max_pages and self.quota.can_afford("search.list"):
                    try:
                        resp = self._search_page(
                            seed["query"],
                            order=order,
                            region_code=region,
                            relevance_language=lang,
                            page_token=token,
                            max_results=page_size,
                        )
                    except QuotaExceededError:
                        self._persist()
                        return new_ids
                    except HttpError:
                        break
                    for item in resp.get("items", []):
                        vid = (item.get("id") or {}).get("videoId")
                        snip = item.get("snippet") or {}
                        ch = snip.get("channelId")
                        if not vid or vid in self.state.discovered() or vid in new_ids:
                            continue
                        if not self._soft_relevant(snip.get("title", ""), snip.get("description", "")):
                            continue
                        if not self._within_strata_caps(seed, ch):
                            continue
                        new_ids.append(vid)
                        if ch:
                            channel_candidates.add(ch)
                            self.state.bump_channel_count(ch, 1)
                        self.state.bump_stratum(f"theme:{seed['theme']}")
                        self.state.bump_stratum(f"age:{seed['target_age_hypothesis']}")
                        self.state.bump_stratum(f"seed:{seed['seed_id']}")
                        if len(new_ids) >= max_new:
                            break
                    token = resp.get("nextPageToken")
                    self.state.set_page_token(query_key, token)
                    pages += 1
                    if not token:
                        self.state.mark_query_done(query_key)
                        break
                if not self.state.get_page_token(query_key):
                    self.state.mark_query_done(query_key)
            seeds_used += 1
            # Mark seed done only if all query variants finished — keep partial resume via tokens
            self._persist()

        # Channel expansion via uploads playlist (GENERAL quota) — prefer over more search
        if (
            yt.get("channel_expansion", {}).get("enabled", True)
            and len(new_ids) < max_new
            and self.quota.can_afford("channels.list")
        ):
            expanded = self._expand_channels(sorted(channel_candidates), max_new - len(new_ids))
            new_ids.extend(expanded)

        self.state.add_discovered(new_ids)
        self.state.note_collection_date()
        self._persist()
        return new_ids

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
                    (ch.get("contentDetails") or {})
                    .get("relatedPlaylists", {})
                    .get("uploads")
                )
                if not uploads:
                    self.state.mark_channel_done(cid)
                    continue
                token = None
                pages = 0
                taken_for_channel = 0
                while (
                    pages < max_pages
                    and taken_for_channel < max_per
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
                        if not vid or vid in self.state.discovered() or vid in out:
                            continue
                        if not self._within_strata_caps(
                            {"theme": "other", "target_age_hypothesis": "UNKNOWN", "seed_id": "channel_exp"},
                            cid,
                        ):
                            continue
                        snip = item.get("snippet") or {}
                        if not self._soft_relevant(snip.get("title", ""), snip.get("description", "")):
                            continue
                        out.append(vid)
                        self.state.bump_channel_count(cid, 1)
                        taken_for_channel += 1
                        if taken_for_channel >= max_per or len(out) >= max_new:
                            break
                    token = presp.get("nextPageToken")
                    pages += 1
                    if not token:
                        break
                self.state.mark_channel_done(cid)
                processed += 1
                self._persist()
        return out

    # ------------------------------------------------------------------ enrichment
    def enrich_video_ids(self, video_ids: Optional[List[str]] = None) -> List[VideoRecord]:
        """ENRICHMENT only — stats/metadata for known IDs. Never calls search.list."""
        if self.youtube is None:
            raise ValueError("API key required for enrichment")
        ids = video_ids if video_ids is not None else self.state.pending_enrichment()
        # Skip already enriched (idempotent)
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

        # 1) Prefer batchGetStats for view/like/comment/duration/publishTime
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
                    # Fall back to videos.list for this batch if batchGetStats unavailable
                    prefer_batch = False
                    break
                for item in resp.get("items", []):
                    stats_by_id[item.get("id")] = item

        # 2) videos.list for status.madeForKids (FACT) + any missing metadata
        need_list = ids if always_status or not prefer_batch else [
            i for i in ids if i not in stats_by_id
        ]
        for i in range(0, len(need_list), batch_list):
            batch = need_list[i : i + batch_list]
            if not self.quota.can_afford("videos.list"):
                break
            try:
                part = "snippet,contentDetails,status,statistics"
                resp = self._videos_list(batch, part=part)
            except QuotaExceededError:
                break
            for item in resp.get("items", []):
                meta_by_id[item["id"]] = item
                if item["id"] not in stats_by_id:
                    stats_by_id[item["id"]] = item

        # 3) Channel enrichment
        channel_ids = sorted(
            {
                (meta_by_id.get(vid) or stats_by_id.get(vid) or {})
                .get("snippet", {})
                .get("channelId")
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

        max_short = int(self.collection.get("target", {}).get("max_duration_seconds_shorts", 60))
        records: List[VideoRecord] = []
        enriched_ids: List[str] = []
        for vid in ids:
            item = meta_by_id.get(vid) or stats_by_id.get(vid)
            if not item:
                continue
            # Merge stats onto meta if separate
            if vid in stats_by_id and vid in meta_by_id:
                merged = dict(meta_by_id[vid])
                for key in ("statistics", "contentDetails", "snippet"):
                    if key in stats_by_id[vid] and key not in merged:
                        merged[key] = stats_by_id[vid][key]
                    elif key in stats_by_id[vid]:
                        # Prefer batch stats numbers when present
                        if key == "statistics":
                            merged[key] = stats_by_id[vid][key]
                item = merged
            ch = channel_cache.get((item.get("snippet") or {}).get("channelId"))
            rec = self._to_record(item, ch, max_short)
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
        max_short: int,
    ) -> Optional[VideoRecord]:
        snip = item.get("snippet", {})
        stats = item.get("statistics", {})
        details = item.get("contentDetails", {})
        status = item.get("status", {})

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

        short_or_long = ShortOrLong.UNKNOWN
        if duration is not None:
            short_or_long = ShortOrLong.SHORT if duration <= max_short else ShortOrLong.LONG
        if duration is not None and duration > 180:
            return None

        # FACT: madeForKids from status
        mfk_raw = status.get("madeForKids")
        if mfk_raw is True:
            made_for_kids = MadeForKids.TRUE
        elif mfk_raw is False:
            made_for_kids = MadeForKids.FALSE
        else:
            made_for_kids = MadeForKids.UNKNOWN

        epoch = classify_views_metric_epoch(
            publish_date=publish_date,
            short_or_long=short_or_long.value,
            break_date=self._break_date(),
        )

        evidence = {
            "views": Evidenced.fact(views, "youtube.videos.statistics").as_dict(),
            "likes": Evidenced.fact(likes, "youtube.videos.statistics").as_dict(),
            "comments": Evidenced.fact(comments, "youtube.videos.statistics").as_dict(),
            "duration_seconds": Evidenced.fact(duration, "youtube.videos.contentDetails").as_dict(),
            "channel_subscribers": Evidenced.fact(subs, "youtube.channels.statistics").as_dict(),
            "made_for_kids": Evidenced.fact(
                made_for_kids.value,
                "YOUTUBE_API",
                confidence=1.0 if made_for_kids != MadeForKids.UNKNOWN else 0.0,
            ).as_dict()
            if made_for_kids != MadeForKids.UNKNOWN
            else Evidenced.unknown("status.madeForKids not present").as_dict(),
            "estimated_target_age": Evidenced.unknown(
                "INFERENCE assigned in Phase 4 — never derived solely from madeForKids"
            ).as_dict(),
            "views_metric_epoch": Evidenced.fact(epoch.value, "shorts_views_break_rule").as_dict(),
        }

        return VideoRecord(
            video_id=item["id"],
            channel_id=snip.get("channelId", ""),
            platform=Platform.YOUTUBE,
            title=snip.get("title"),
            description=snip.get("description"),
            publish_date=publish_date,
            duration_seconds=duration,
            views=views,
            likes=likes,
            comments=comments,
            views_per_day=vpd,
            channel_subscribers=subs,
            video_count=vcount,
            language=language,
            country=country,
            short_or_long=short_or_long,
            made_for_kids=made_for_kids,
            views_metric_epoch=epoch.value,
            channel_size_bucket=channel_size_bucket(subs),
            field_evidence=evidence,
            collected_at=utcnow(),
            source="youtube_data_api_v3",
        )

    def _break_date(self) -> date:
        raw = (
            self.collection.get("shorts_views_metric_break", {}).get("break_date")
            or "2025-03-31"
        )
        return date.fromisoformat(raw)

    def _persist(self) -> None:
        self.state.set_quota_usage(self.quota.snapshot())
        self.state.save()

    def collect(self, max_videos: int = 500) -> List[VideoRecord]:
        """Discover then enrich up to max_videos (multi-day resume-safe)."""
        need = max(0, max_videos - len(self.state.enriched()))
        if need > 0:
            # Discover more if pending enrichment is insufficient
            pending = self.state.pending_enrichment()
            if len(pending) < need:
                self.discover_video_ids(need - len(pending))
        records = self.enrich_video_ids()
        # Cap to target for this stage
        return records[:max_videos]
