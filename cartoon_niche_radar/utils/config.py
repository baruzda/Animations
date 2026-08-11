from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    youtube_api_key: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    classifier_provider: str = "heuristic"
    enable_tiktok_public: bool = False
    enable_instaloader: bool = False
    enable_google_trends: bool = True
    database_url: str = "sqlite:///data/cartoon_niche_radar.db"
    youtube_max_results_per_query: int = 50
    youtube_daily_quota_budget: int = 8000
    min_confidence_for_label: float = 0.55


def load_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config {name} must be a mapping")
    return data


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_scoring_config() -> dict[str, Any]:
    return load_yaml("scoring.yaml")


@lru_cache
def get_taxonomy() -> dict[str, Any]:
    return load_yaml("taxonomy.yaml")


@lru_cache
def get_sources_config() -> dict[str, Any]:
    return load_yaml("sources.yaml")


@lru_cache
def get_collection_config() -> dict[str, Any]:
    return load_yaml("collection.yaml")


@lru_cache
def get_quota_config() -> dict[str, Any]:
    return load_yaml("quota.yaml")


def clear_config_caches() -> None:
    get_settings.cache_clear()
    get_scoring_config.cache_clear()
    get_taxonomy.cache_clear()
    get_sources_config.cache_clear()
    get_collection_config.cache_clear()
    get_quota_config.cache_clear()


def project_paths() -> dict[str, Path]:
    return {
        "root": ROOT,
        "data": ROOT / "data",
        "raw": ROOT / "data" / "raw",
        "normalized": ROOT / "data" / "normalized",
        "classified": ROOT / "data" / "classified",
        "scored": ROOT / "data" / "scored",
        "reports": ROOT / "data" / "reports",
        "outputs": ROOT / "outputs",
        "qa": ROOT / "data" / "reports" / "qa",
    }
