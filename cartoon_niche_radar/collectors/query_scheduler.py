from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from cartoon_niche_radar.utils.config import get_collection_config, get_quota_config, project_paths
from cartoon_niche_radar.utils.time import utcnow


def _published_after_iso(lookback_days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=int(lookback_days))
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


class QueryScheduler:
    """Deterministic daily SEARCH budget planner (round-robin across dimensions)."""

    def __init__(self, collection: Optional[Dict[str, Any]] = None, quota: Optional[Dict[str, Any]] = None) -> None:
        self.collection = collection or get_collection_config()
        self.quota = quota or get_quota_config()
        self.plan_path = project_paths()["raw"] / "daily_query_plan.json"

    def search_daily_limit(self) -> int:
        return int(self.quota.get("buckets", {}).get("SEARCH", {}).get("daily_limit", 100))

    def lookback_days(self) -> int:
        return int(self.collection.get("target", {}).get("lookback_days", 365))

    def published_after(self) -> str:
        return _published_after_iso(self.lookback_days())

    def build_plan(
        self,
        seeds: List[Dict[str, str]],
        *,
        pt_quota_date: str,
        max_calls: Optional[int] = None,
    ) -> Dict[str, Any]:
        yt = self.collection.get("youtube", {})
        search_cfg = yt.get("search", {})
        orders = list(search_cfg.get("order_modes") or ["date", "relevance", "viewCount"])
        regions = list(search_cfg.get("region_codes") or ["US"])
        langs = list(search_cfg.get("relevance_languages") or ["en"])
        max_pages = int(search_cfg.get("max_pages_per_query", 1))
        # Scheduler distributes CALLS, not pages-within-call; each planned slot = 1 search.list call
        budget = min(self.search_daily_limit(), max_calls or self.search_daily_limit())

        # Explicit omissions for Stage QA (none by default — all configured orders included)
        omitted = {
            "orders_omitted": [],
            "regions_truncated_for_budget": False,
            "languages_truncated_for_budget": False,
            "note": "All configured order_modes are eligible; budget may leave some slots unexecuted.",
        }

        # Build cartesian candidates, then round-robin pick until budget
        candidates: List[Dict[str, Any]] = []
        for seed in seeds:
            for order in orders:
                for region in regions:
                    for lang in langs:
                        candidates.append(
                            {
                                "query_key": f"{seed['seed_id']}|{order}|{region}|{lang}",
                                "seed_id": seed["seed_id"],
                                "query": seed["query"],
                                "theme": seed.get("theme", "other"),
                                "sample_role": seed.get("sample_role", "CORE"),
                                "source_seed_family": seed.get("source_seed_family", seed.get("seed_id")),
                                "order": order,
                                "region": region,
                                "language": lang,
                                "publishedAfter": self.published_after(),
                                "lookback_days": self.lookback_days(),
                                "max_pages": max_pages,
                                "status": "planned",
                            }
                        )

        # Round-robin by theme while rotating preferred order to avoid early-order domination
        by_theme: Dict[str, List[Dict[str, Any]]] = {}
        for c in candidates:
            by_theme.setdefault(c["theme"], []).append(c)
        theme_keys = sorted(by_theme.keys())
        planned: List[Dict[str, Any]] = []
        idx = 0
        while len(planned) < budget and any(by_theme.values()):
            t = theme_keys[idx % len(theme_keys)]
            desired_order = orders[idx % len(orders)] if orders else None
            if by_theme[t]:
                pick = None
                if desired_order is not None:
                    for i, c in enumerate(by_theme[t]):
                        if c["order"] == desired_order:
                            pick = by_theme[t].pop(i)
                            break
                if pick is None:
                    pick = by_theme[t].pop(0)
                planned.append(pick)
            idx += 1
            if idx > len(candidates) * 5:
                break

        # If still under budget (few candidates), fill remaining in order
        leftover = [c for cs in by_theme.values() for c in cs]
        for c in leftover:
            if len(planned) >= budget:
                break
            planned.append(c)

        coverage = {
            "themes": sorted({p["theme"] for p in planned}),
            "orders": sorted({p["order"] for p in planned}),
            "regions": sorted({p["region"] for p in planned}),
            "languages": sorted({p["language"] for p in planned}),
            "sample_roles": sorted({p["sample_role"] for p in planned}),
            "n_themes_configured": len(theme_keys),
            "n_orders_configured": len(orders),
            "n_regions_configured": len(regions),
            "n_languages_configured": len(langs),
        }
        plan = {
            "pt_quota_date": pt_quota_date,
            "created_at": utcnow().isoformat(),
            "planned_search_calls": len(planned),
            "search_daily_limit": self.search_daily_limit(),
            "publishedAfter": self.published_after(),
            "lookback_days": self.lookback_days(),
            "omitted_dimensions": omitted,
            "coverage_by_dimension": coverage,
            "slots": planned,
            "executed_search_calls": 0,
            "completed_query_keys": [],
        }
        return plan

    def save_plan(self, plan: Dict[str, Any]) -> Path:
        self.plan_path.parent.mkdir(parents=True, exist_ok=True)
        self.plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
        return self.plan_path

    def load_plan(self) -> Optional[Dict[str, Any]]:
        if not self.plan_path.exists():
            return None
        return json.loads(self.plan_path.read_text(encoding="utf-8"))

    def load_or_build(
        self,
        seeds: List[Dict[str, str]],
        *,
        pt_quota_date: str,
        max_calls: Optional[int] = None,
    ) -> Dict[str, Any]:
        existing = self.load_plan()
        if existing and existing.get("pt_quota_date") == pt_quota_date:
            return existing
        plan = self.build_plan(seeds, pt_quota_date=pt_quota_date, max_calls=max_calls)
        self.save_plan(plan)
        return plan

    def mark_executed(self, plan: Dict[str, Any], query_key: str, *, success: bool) -> Dict[str, Any]:
        plan["executed_search_calls"] = int(plan.get("executed_search_calls") or 0) + 1
        for slot in plan.get("slots") or []:
            if slot.get("query_key") == query_key:
                slot["status"] = "done" if success else "failed"
                slot["executed_at"] = utcnow().isoformat()
                break
        done = set(plan.get("completed_query_keys") or [])
        done.add(query_key)
        plan["completed_query_keys"] = sorted(done)
        self.save_plan(plan)
        return plan
