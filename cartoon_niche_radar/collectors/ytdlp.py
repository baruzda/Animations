from __future__ import annotations

import shutil
import subprocess
from typing import Any

from cartoon_niche_radar.models.evidence import Evidenced


class YtDlpEnricher:
    """Optional enrichment for known public video IDs via yt-dlp."""

    def __init__(self) -> None:
        if not shutil.which("yt-dlp"):
            raise RuntimeError(
                "yt-dlp not found on PATH. Install optional extra: pip install '.[ytdlp]' "
                "and ensure yt-dlp binary is available."
            )

    def enrich_youtube(self, video_id: str) -> dict[str, Any]:
        url = f"https://www.youtube.com/watch?v={video_id}"
        cmd = [
            "yt-dlp",
            "--skip-download",
            "--print",
            "%()j",
            url,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            return {
                "ok": False,
                "error": proc.stderr.strip() or "yt-dlp failed",
                "evidence": Evidenced.unknown("yt-dlp enrichment failed").as_dict(),
            }
        # yt-dlp JSON print can be large; parse lazily via json in caller if needed
        import json

        data = json.loads(proc.stdout)
        duration = data.get("duration")
        if duration is None and data.get("duration_string"):
            # leave UNKNOWN if only string form
            duration = None
        return {
            "ok": True,
            "duration_seconds": duration,
            "view_count": data.get("view_count"),
            "like_count": data.get("like_count"),
            "language": data.get("language"),
            "tags": data.get("tags") or [],
            "evidence": {
                "duration_seconds": Evidenced.fact(
                    duration, "yt-dlp", confidence=0.95
                ).as_dict()
                if duration is not None
                else Evidenced.unknown("duration missing in yt-dlp").as_dict(),
            },
        }
