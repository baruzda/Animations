from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from cartoon_niche_radar.utils.config import load_yaml, project_paths
from cartoon_niche_radar.utils.time import utcnow


class QuotaExceededError(RuntimeError):
    """Raised when an API call would exceed a configured bucket limit."""


@dataclass
class QuotaCallRecord:
    endpoint: str
    quota_bucket: str
    estimated_cost: int
    timestamp: str
    pt_quota_date: str
    request_parameters_hash: str
    success: bool
    error: Optional[str] = None


class QuotaManager:
    """Config-driven granular YouTube quota accounting (PT daily reset)."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or load_yaml("quota.yaml")
        self.tz = ZoneInfo(self.config.get("timezone", "America/Los_Angeles"))
        self.buckets_cfg: Dict[str, Any] = self.config.get("buckets", {})
        self.stop_before = bool(self.config.get("stop_before_exceed", True))
        self.reserve = dict(self.config.get("reserve_calls") or {})
        self.spent: Dict[str, int] = {name: 0 for name in self.buckets_cfg}
        self._endpoint_index = self._build_endpoint_index()
        self._log_path = self._resolve_log_path()
        self._active_pt_date = self.pt_quota_date()

    def _build_endpoint_index(self) -> Dict[str, tuple[str, int]]:
        index: Dict[str, tuple[str, int]] = {}
        for bucket, cfg in self.buckets_cfg.items():
            for endpoint, meta in (cfg.get("endpoints") or {}).items():
                index[endpoint] = (bucket, int(meta.get("cost", 1)))
        return index

    def _resolve_log_path(self) -> Path:
        rel = (self.config.get("logging") or {}).get("path", "data/raw/quota_calls.jsonl")
        path = Path(rel)
        if not path.is_absolute():
            path = project_paths()["root"] / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def pt_now(self) -> datetime:
        return utcnow().astimezone(self.tz)

    def pt_quota_date(self) -> str:
        return self.pt_now().date().isoformat()

    def maybe_roll_day(self) -> None:
        today = self.pt_quota_date()
        if today != self._active_pt_date:
            self.spent = {name: 0 for name in self.buckets_cfg}
            self._active_pt_date = today

    def resolve(self, endpoint: str) -> tuple[str, int]:
        if endpoint in self._endpoint_index:
            return self._endpoint_index[endpoint]
        general = self.buckets_cfg.get("GENERAL", {})
        return "GENERAL", int(general.get("default_endpoint_cost", 1))

    def remaining(self, bucket: str) -> int:
        self.maybe_roll_day()
        limit = int(self.buckets_cfg.get(bucket, {}).get("daily_limit", 0))
        reserve = int(self.reserve.get(bucket, 0))
        return max(0, limit - reserve - self.spent.get(bucket, 0))

    def can_afford(self, endpoint: str, cost: Optional[int] = None) -> bool:
        bucket, default_cost = self.resolve(endpoint)
        units = int(default_cost if cost is None else cost)
        rem = self.remaining(bucket)
        if self.stop_before:
            return rem >= units
        return rem > 0

    def check_or_raise(self, endpoint: str, cost: Optional[int] = None) -> tuple[str, int]:
        bucket, default_cost = self.resolve(endpoint)
        units = int(default_cost if cost is None else cost)
        if not self.can_afford(endpoint, units):
            raise QuotaExceededError(
                f"Would exceed quota bucket={bucket} endpoint={endpoint} "
                f"need={units} remaining={self.remaining(bucket)} "
                f"pt_date={self.pt_quota_date()}"
            )
        return bucket, units

    @staticmethod
    def hash_params(params: Dict[str, Any]) -> str:
        blob = json.dumps(params, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    def charge(
        self,
        endpoint: str,
        params: Dict[str, Any],
        *,
        success: bool,
        error: Optional[str] = None,
        cost: Optional[int] = None,
    ) -> QuotaCallRecord:
        bucket, units = self.check_or_raise(endpoint, cost)
        # Only spend on attempted calls that passed the pre-check.
        self.spent[bucket] = self.spent.get(bucket, 0) + units
        record = QuotaCallRecord(
            endpoint=endpoint,
            quota_bucket=bucket,
            estimated_cost=units,
            timestamp=utcnow().isoformat(),
            pt_quota_date=self.pt_quota_date(),
            request_parameters_hash=self.hash_params(params),
            success=success,
            error=error,
        )
        if (self.config.get("logging") or {}).get("enabled", True):
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
        return record

    def snapshot(self) -> Dict[str, Any]:
        self.maybe_roll_day()
        return {
            "pt_quota_date": self.pt_quota_date(),
            "spent": dict(self.spent),
            "remaining": {b: self.remaining(b) for b in self.buckets_cfg},
            "limits": {
                b: int(cfg.get("daily_limit", 0)) for b, cfg in self.buckets_cfg.items()
            },
        }

    def load_spent(self, spent: Dict[str, int], pt_quota_date: Optional[str] = None) -> None:
        if pt_quota_date and pt_quota_date != self.pt_quota_date():
            # Stale day — ignore and start fresh for today
            self.spent = {name: 0 for name in self.buckets_cfg}
            self._active_pt_date = self.pt_quota_date()
            return
        self.spent = {name: int(spent.get(name, 0)) for name in self.buckets_cfg}
        self._active_pt_date = pt_quota_date or self.pt_quota_date()
