from __future__ import annotations

import shutil
import subprocess
from typing import Any, Dict, Optional

from cartoon_niche_radar.models.evidence import Evidenced


class YtDlpEnricher:
    """Optional public-surface enrichment via yt-dlp (config-driven).

    May supply tags, captions excerpts, width/height, and best-effort Shorts-tab
    membership hints. All derived labels remain INFERENCE — never FACT Shorts
    confirmation unless membership signal is explicit and recorded.
    """

    def __init__(self) -> None:
        if not shutil.which("yt-dlp"):
            raise RuntimeError(
                "yt-dlp not found on PATH. Install optional extra: pip install '.[ytdlp]'"
            )

    def enrich_youtube(self, video_id: str) -> Dict[str, Any]:
        url = f"https://www.youtube.com/watch?v={video_id}"
        cmd = ["yt-dlp", "--skip-download", "--print", "%()j", url]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            return {
                "ok": False,
                "error": proc.stderr.strip() or "yt-dlp failed",
                "evidence": Evidenced.unknown("yt-dlp enrichment failed").as_dict(),
            }
        import json

        data = json.loads(proc.stdout)
        width = data.get("width")
        height = data.get("height")
        # Best-effort: some extractors expose webpage_url with /shorts/
        webpage = str(data.get("webpage_url") or data.get("original_url") or "")
        is_shorts_url = "/shorts/" in webpage.lower()
        return {
            "ok": True,
            "duration_seconds": data.get("duration"),
            "view_count": data.get("view_count"),
            "like_count": data.get("like_count"),
            "language": data.get("language"),
            "tags": data.get("tags") or [],
            "width": width,
            "height": height,
            "webpage_url": webpage,
            "is_shorts_url": is_shorts_url,
            "captions_available": bool(data.get("subtitles") or data.get("automatic_captions")),
            "evidence": {
                "duration_seconds": Evidenced.fact(
                    data.get("duration"), "yt-dlp", confidence=0.95
                ).as_dict()
                if data.get("duration") is not None
                else Evidenced.unknown("duration missing in yt-dlp").as_dict(),
                "aspect": Evidenced.inference(
                    {"width": width, "height": height},
                    0.8,
                    "yt-dlp",
                    rationale="public format metadata",
                ).as_dict()
                if width and height
                else Evidenced.unknown("no width/height").as_dict(),
                "shorts_url_hint": Evidenced.inference(
                    is_shorts_url, 0.85 if is_shorts_url else 0.2, "yt-dlp.webpage_url"
                ).as_dict(),
            },
        }

    def channel_shorts_tab_probe(self, channel_url: str) -> Dict[str, Any]:
        """Experimental: probe public channel Shorts tab listing (optional)."""
        shorts_url = channel_url.rstrip("/") + "/shorts"
        cmd = [
            "yt-dlp",
            "--skip-download",
            "--flat-playlist",
            "--print",
            "%(id)s",
            shorts_url,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            return {
                "ok": False,
                "ids": [],
                "evidence": Evidenced.unknown("shorts tab probe failed").as_dict(),
            }
        ids = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        return {
            "ok": True,
            "ids": ids,
            "evidence": Evidenced.inference(
                True, 0.7, "yt-dlp.channel_shorts_tab", rationale=f"n={len(ids)}"
            ).as_dict(),
        }
