from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from cartoon_niche_radar.utils.config import get_collection_config, project_paths
from cartoon_niche_radar.utils.time import utcnow


class CollectionState:
    """Resume-safe multi-day collection state (idempotent)."""

    def __init__(self, path: Optional[Path] = None) -> None:
        cfg = get_collection_config().get("resume", {})
        rel = cfg.get("state_path", "data/raw/collection_state.json")
        self.path = path or (project_paths()["root"] / rel)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data: Dict[str, Any] = {
            "version": 2,
            "updated_at": None,
            "completed_queries": [],
            "completed_seeds": [],
            "completed_channels": [],
            "channel_video_counts": {},
            "query_page_tokens": {},
            "discovered_video_ids": [],
            "enriched_video_ids": [],
            "video_meta": {},  # video_id -> {sample_role, theme, seed_id, ...}
            "quota_usage": {},
            "quota_pt_date": None,
            "collection_dates": [],
            "stage": None,
            "strata_counts": {},
        }
        self.load()

    def load(self) -> None:
        if self.path.exists():
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            self.data.update(loaded)

    def save(self) -> None:
        self.data["updated_at"] = utcnow().isoformat()
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")

    def is_query_done(self, query_key: str) -> bool:
        return query_key in set(self.data.get("completed_queries") or [])

    def mark_query_done(self, query_key: str) -> None:
        done = set(self.data.get("completed_queries") or [])
        done.add(query_key)
        self.data["completed_queries"] = sorted(done)

    def is_seed_done(self, seed: str) -> bool:
        return seed in set(self.data.get("completed_seeds") or [])

    def mark_seed_done(self, seed: str) -> None:
        done = set(self.data.get("completed_seeds") or [])
        done.add(seed)
        self.data["completed_seeds"] = sorted(done)

    def is_channel_done(self, channel_id: str) -> bool:
        return channel_id in set(self.data.get("completed_channels") or [])

    def mark_channel_done(self, channel_id: str) -> None:
        done = set(self.data.get("completed_channels") or [])
        done.add(channel_id)
        self.data["completed_channels"] = sorted(done)

    def get_page_token(self, query_key: str) -> Optional[str]:
        return (self.data.get("query_page_tokens") or {}).get(query_key)

    def set_page_token(self, query_key: str, token: Optional[str]) -> None:
        tokens = dict(self.data.get("query_page_tokens") or {})
        if token:
            tokens[query_key] = token
        else:
            tokens.pop(query_key, None)
        self.data["query_page_tokens"] = tokens

    def discovered(self) -> Set[str]:
        return set(self.data.get("discovered_video_ids") or [])

    def enriched(self) -> Set[str]:
        return set(self.data.get("enriched_video_ids") or [])

    def effective_discovered_count(self) -> int:
        """Denominator for strata/channel caps = persisted discovered count."""
        return len(self.discovered())

    def add_discovered(self, video_ids: Iterable[str]) -> int:
        current = self.discovered()
        before = len(current)
        current.update(video_ids)
        self.data["discovered_video_ids"] = sorted(current)
        return len(current) - before

    def accept_discovered(
        self,
        video_id: str,
        *,
        channel_id: Optional[str] = None,
        theme: Optional[str] = None,
        age_hypothesis: Optional[str] = None,
        seed_id: Optional[str] = None,
        sample_role: str = "CORE",
        source_seed_family: Optional[str] = None,
        persist: bool = True,
    ) -> bool:
        """Persist a newly accepted ID immediately (crash-safe) and bump strata.

        Returns False if already discovered.
        """
        if video_id in self.discovered():
            return False
        ids = self.discovered()
        ids.add(video_id)
        self.data["discovered_video_ids"] = sorted(ids)

        meta = dict(self.data.get("video_meta") or {})
        meta[video_id] = {
            "channel_id": channel_id,
            "theme": theme,
            "age_hypothesis": age_hypothesis,
            "seed_id": seed_id,
            "sample_role": sample_role,
            "source_seed_family": source_seed_family or seed_id,
            "accepted_at": utcnow().isoformat(),
        }
        self.data["video_meta"] = meta

        if channel_id:
            self.bump_channel_count(channel_id, 1)
        if theme:
            self.bump_stratum(f"theme:{theme}")
        if age_hypothesis:
            self.bump_stratum(f"age:{age_hypothesis}")
        if seed_id:
            self.bump_stratum(f"seed:{seed_id}")
        self.bump_stratum(f"sample_role:{sample_role}")
        if persist:
            self.save()
        return True

    def add_enriched(self, video_ids: Iterable[str]) -> int:
        current = self.enriched()
        before = len(current)
        current.update(video_ids)
        self.data["enriched_video_ids"] = sorted(current)
        return len(current) - before

    def pending_enrichment(self) -> List[str]:
        return sorted(self.discovered() - self.enriched())

    def bump_channel_count(self, channel_id: str, n: int = 1) -> int:
        counts = dict(self.data.get("channel_video_counts") or {})
        counts[channel_id] = int(counts.get(channel_id, 0)) + n
        self.data["channel_video_counts"] = counts
        return counts[channel_id]

    def channel_share(self, channel_id: str, total: Optional[int] = None) -> float:
        total = total if total is not None else max(1, self.effective_discovered_count())
        counts = self.data.get("channel_video_counts") or {}
        return float(counts.get(channel_id, 0)) / float(total)

    def stratum_share(self, key: str, total: Optional[int] = None) -> float:
        total = total if total is not None else max(1, self.effective_discovered_count())
        counts = self.data.get("strata_counts") or {}
        return float(counts.get(key, 0)) / float(total)

    def note_collection_date(self) -> None:
        dates = list(self.data.get("collection_dates") or [])
        day = utcnow().date().isoformat()
        if day not in dates:
            dates.append(day)
        self.data["collection_dates"] = dates

    def set_quota_usage(self, snapshot: Dict[str, Any]) -> None:
        self.data["quota_usage"] = snapshot.get("spent", {})
        self.data["quota_pt_date"] = snapshot.get("pt_quota_date")

    def bump_stratum(self, key: str, n: int = 1) -> None:
        strata = dict(self.data.get("strata_counts") or {})
        strata[key] = int(strata.get(key, 0)) + n
        self.data["strata_counts"] = strata
