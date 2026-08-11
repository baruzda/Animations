from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Iterable, List


class FFmpegUnavailable(RuntimeError):
    pass


def ffmpeg_available() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def write_concat_file(video_paths: Iterable[Path], target: Path) -> Path:
    paths = list(video_paths)
    if not paths:
        raise ValueError("at least one video path is required")
    target.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []
    for path in paths:
        escaped = str(path.resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def build_assembly_command(concat_file: Path, output_path: Path) -> List[str]:
    return [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-vf",
        "scale=720:1280:force_original_aspect_ratio=decrease,"
        "pad=720:1280:(ow-iw)/2:(oh-ih)/2",
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-an",
        str(output_path),
    ]


def assemble_videos(video_paths: Iterable[Path], output_path: Path) -> Path:
    if not ffmpeg_available():
        raise FFmpegUnavailable("ffmpeg and ffprobe are required")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    concat_file = output_path.with_suffix(".concat.txt")
    write_concat_file(video_paths, concat_file)
    command = build_assembly_command(concat_file, output_path)
    subprocess.run(command, check=True, capture_output=True, text=True)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("ffmpeg completed without a non-empty output file")
    return output_path
