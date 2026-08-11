from __future__ import annotations

from typing import Any

from cartoon_niche_radar.models.evidence import Evidenced
from cartoon_niche_radar.utils.config import get_settings


class GoogleTrendsSignal:
    """Secondary demand signal only — never treated as monetization proof."""

    def __init__(self) -> None:
        self.enabled = get_settings().enable_google_trends

    def interest_over_time(self, keywords: list[str], timeframe: str = "today 12-m") -> dict[str, Any]:
        if not self.enabled:
            return {
                "status": "skipped",
                "kind": "UNKNOWN",
                "evidence": Evidenced.unknown("Google Trends disabled").as_dict(),
                "series": {},
            }
        try:
            from pytrends.request import TrendReq
        except ImportError as exc:
            raise RuntimeError("pytrends is required for Google Trends signals") from exc

        # pytrends is brittle; failures become UNKNOWN rather than invented numbers.
        try:
            pytrends = TrendReq(hl="en-US", tz=360)
            # Google Trends caps at 5 terms per request
            chunks = [keywords[i : i + 5] for i in range(0, len(keywords), 5)]
            series: dict[str, list[float]] = {}
            for chunk in chunks:
                pytrends.build_payload(chunk, timeframe=timeframe)
                df = pytrends.interest_over_time()
                if df is None or df.empty:
                    continue
                for col in chunk:
                    if col in df.columns:
                        series[col] = [float(x) for x in df[col].tolist()]
            return {
                "status": "ok",
                "kind": "FACT",
                "source": "google_trends",
                "note": "Secondary signal only; not a Shorts performance proof.",
                "series": series,
                "evidence": Evidenced.fact(series, "google_trends", confidence=0.7).as_dict(),
            }
        except Exception as exc:  # noqa: BLE001 — external scraper fragility
            return {
                "status": "error",
                "kind": "UNKNOWN",
                "error": str(exc),
                "series": {},
                "evidence": Evidenced.unknown(f"Google Trends failed: {exc}").as_dict(),
            }
