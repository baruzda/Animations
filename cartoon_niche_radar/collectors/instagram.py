from __future__ import annotations

from cartoon_niche_radar.models.evidence import Evidenced
from cartoon_niche_radar.utils.config import get_settings, get_sources_config


class InstagramCollector:
    """Experimental Instaloader-based Reels metadata collector (public only)."""

    def __init__(self) -> None:
        sources = get_sources_config()
        experimental = sources.get("experimental", {}).get("instaloader", {})
        settings = get_settings()
        self.enabled = bool(experimental.get("enabled")) and settings.enable_instaloader

    def collect_hashtag(self, hashtag: str, max_posts: int = 100) -> dict:
        if not self.enabled:
            return {
                "status": "skipped",
                "kind": "UNKNOWN",
                "reason": "Instaloader collector disabled (experimental).",
                "records": [],
                "evidence": Evidenced.unknown("Instagram data not collected").as_dict(),
            }
        try:
            import instaloader  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "ENABLE_INSTALOADER=true but instaloader is not installed. "
                "pip install '.[instagram]'"
            ) from exc

        # Privacy: do not store commenter PII / comment text.
        _ = hashtag, max_posts, instaloader
        return {
            "status": "not_implemented_rate_limited",
            "kind": "UNKNOWN",
            "reason": (
                "Instaloader path is scaffolded but not auto-run to avoid ToS/rate-limit risk. "
                "Wire a reviewed public-hashtag fetch before enabling in production collection."
            ),
            "records": [],
            "evidence": Evidenced.unknown("Instagram collection not executed").as_dict(),
        }
