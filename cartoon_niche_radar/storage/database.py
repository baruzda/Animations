from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from cartoon_niche_radar.models.schemas import VideoRecord
from cartoon_niche_radar.utils.config import get_settings, project_paths
from cartoon_niche_radar.utils.time import utcnow


class Base(DeclarativeBase):
    pass


class VideoRow(Base):
    __tablename__ = "videos"

    video_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(64), index=True)
    platform: Mapped[str] = mapped_column(String(32), default="youtube")
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    publish_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    views: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    likes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    comments: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    views_per_day: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    channel_subscribers: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    video_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    short_or_long: Mapped[str] = mapped_column(String(16), default="unknown")
    topic: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    estimated_target_age: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    visual_style: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    dialogue: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    music: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    recurring_character: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    series: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    made_for_kids: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    views_metric_epoch: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="youtube_data_api_v3")
    field_evidence: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    collected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)


class ClassificationRow(Base):
    __tablename__ = "classifications"

    video_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON)
    classifier: Mapped[str] = mapped_column(String(64))
    classified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


def _ensure_parent(url: str) -> None:
    if url.startswith("sqlite:///"):
        path = Path(url.replace("sqlite:///", "", 1))
        if not path.is_absolute():
            path = project_paths()["root"] / path
        path.parent.mkdir(parents=True, exist_ok=True)


def get_engine(url: Optional[str] = None):
    settings = get_settings()
    db_url = url or settings.database_url
    _ensure_parent(db_url)
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    return create_engine(db_url, future=True, connect_args=connect_args)


def init_db(url: Optional[str] = None) -> sessionmaker:
    engine = get_engine(url)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def upsert_videos(session: Session, records: Iterable[VideoRecord]) -> int:
    count = 0
    for rec in records:
        existing = session.get(VideoRow, rec.video_id)
        payload = rec.model_dump(mode="json")
        evidence = payload.pop("field_evidence", {})
        bool_fields = {
            "dialogue": None if rec.dialogue is None else int(rec.dialogue),
            "music": None if rec.music is None else int(rec.music),
            "recurring_character": None
            if rec.recurring_character is None
            else int(rec.recurring_character),
            "series": None if rec.series is None else int(rec.series),
        }
        row_data = {
            **{k: v for k, v in payload.items() if k not in bool_fields},
            **bool_fields,
            "platform": rec.platform.value if hasattr(rec.platform, "value") else rec.platform,
            "short_or_long": rec.short_or_long.value
            if hasattr(rec.short_or_long, "value")
            else rec.short_or_long,
            "made_for_kids": rec.made_for_kids.value
            if hasattr(rec.made_for_kids, "value")
            else rec.made_for_kids,
            "views_metric_epoch": rec.views_metric_epoch,
            "field_evidence": evidence,
            "collected_at": rec.collected_at or utcnow(),
        }
        if existing is None:
            session.add(VideoRow(**row_data))
        else:
            for k, v in row_data.items():
                setattr(existing, k, v)
        count += 1
    session.commit()
    return count


def count_videos(session: Session) -> int:
    return len(session.scalars(select(VideoRow.video_id)).all())


def export_videos_jsonl(session: Session, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for row in session.scalars(select(VideoRow)):
            f.write(
                json.dumps(
                    {c.name: getattr(row, c.name) for c in row.__table__.columns},
                    default=str,
                )
            )
            f.write("\n")
            n += 1
    return n
