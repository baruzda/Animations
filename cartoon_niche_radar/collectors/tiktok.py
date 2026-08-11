from __future__ import annotations

from cartoon_niche_radar.models.evidence import Evidenced
from cartoon_niche_radar.utils.config import get_settings, get_sources_config


class TikTokCollector:
    """Experimental public TikTok collector.

    FACT: TikTok Research API is prohibited for commercial use under current ToS.
    This class never calls Research API endpoints.
    """

    def __init__(self) -> None:
        sources = get_sources_config()
        experimental = sources.get("experimental", {}).get("tiktok_api_public", {})
        settings = get_settings()
        self.enabled = bool(experimental.get("enabled")) and settings.enable_tiktok_public
        if experimental.get("research_api_allowed") is True:
            raise RuntimeError(
                "Config violation: research_api_allowed must remain false for commercial projects."
            )

    def collect(self, *_args, **_kwargs):
        if not self.enabled:
            return {
                "status": "skipped",
                "kind": "UNKNOWN",
                "reason": (
                    "TikTok public collector disabled. Research API is blocked for commercial "
                    "use (FACT). Enable experimental TikTok-Api only after confirming current "
                    "platform restrictions allow your intended public-data use."
                ),
                "records": [],
                "evidence": Evidenced.unknown(
                    "TikTok data not collected in this run"
                ).as_dict(),
            }

        # Soft dependency — only import if explicitly enabled
        try:
            from TikTokApi import TikTokApi  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "ENABLE_TIKTOK_PUBLIC=true but TikTokApi is not installed. "
                "pip install '.[tiktok]'"
            ) from exc

        # Intentionally minimal stub: callers must supply a compliant session strategy.
        return {
            "status": "not_implemented_session",
            "kind": "UNKNOWN",
            "reason": (
                "INFERENCE: Unofficial TikTok-Api requires a valid public session strategy "
                "and may violate platform ToS depending on method. Implement only after legal "
                "review. No records returned."
            ),
            "records": [],
            "api_ref": str(TikTokApi),
            "evidence": Evidenced.unknown(
                "TikTok session strategy not configured"
            ).as_dict(),
        }
