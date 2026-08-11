"""Thin wrapper — prefer: python -m cartoon_niche_radar.pipeline.sample via package API."""

from cartoon_niche_radar.pipeline.sample import generate_sample

if __name__ == "__main__":
    generate_sample()
    print("Wrote synthetic sample to data/raw/youtube_videos.jsonl")
