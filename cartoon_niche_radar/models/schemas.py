from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from cartoon_niche_radar.models.evidence import Evidenced, EvidenceKind


class Platform(str, Enum):
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"


class ShortOrLong(str, Enum):
    SHORT = "short"
    LONG = "long"
    UNKNOWN = "unknown"


class ChannelSizeBucket(str, Enum):
    MICRO = "micro"
    SMALL = "small"
    MID = "mid"
    MEGA = "mega"
    UNKNOWN = "unknown"


class MadeForKids(str, Enum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


class VideoRecord(BaseModel):
    """Canonical per-video schema for Phase 2 dataset."""

    video_id: str
    channel_id: str
    platform: Platform = Platform.YOUTUBE
    title: Optional[str] = None
    description: Optional[str] = None
    publish_date: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    views_per_day: Optional[float] = None
    channel_subscribers: Optional[int] = None
    video_count: Optional[int] = None
    language: Optional[str] = None
    country: Optional[str] = None
    short_or_long: ShortOrLong = ShortOrLong.UNKNOWN
    topic: Optional[str] = None
    estimated_target_age: Optional[str] = None
    visual_style: Optional[str] = None
    dialogue: Optional[bool] = None
    music: Optional[bool] = None
    recurring_character: Optional[bool] = None
    series: Optional[bool] = None

    # FACT from YouTube status.madeForKids — never equated to a specific age band
    made_for_kids: MadeForKids = MadeForKids.UNKNOWN
    # Shorts view-count methodology epoch
    views_metric_epoch: str = "UNKNOWN"
    channel_size_bucket: Optional[str] = None

    field_evidence: Dict[str, Any] = Field(default_factory=dict)
    collected_at: Optional[datetime] = None
    source: str = "youtube_data_api_v3"

    @field_validator("views", "likes", "comments", "channel_subscribers", "video_count")
    @classmethod
    def non_negative(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("counts must be non-negative")
        return v


class NormalizedMetrics(BaseModel):
    video_id: str
    views_per_day: Optional[float] = None
    views_per_subscriber: Optional[float] = None
    engagement_rate: Optional[float] = None
    like_rate: Optional[float] = None
    comment_rate: Optional[float] = None
    viral_coefficient: Optional[float] = None
    channel_size_bucket: ChannelSizeBucket = ChannelSizeBucket.UNKNOWN
    channel_size_adjusted_performance: Optional[float] = None
    age_days: Optional[float] = None
    views_metric_epoch: str = "UNKNOWN"
    opportunity_eligible: bool = False


class ClassificationResult(BaseModel):
    video_id: str
    target_age: Evidenced[str]
    theme: Evidenced[str]
    story_structure: Evidenced[str]
    hook: Evidenced[str]
    visual_style: Evidenced[str]
    character_type: Evidenced[str]
    emotional_trigger: Evidenced[str]
    format: Evidenced[str]
    series_potential: Evidenced[str]
    dialogue: Evidenced[bool]
    music: Evidenced[bool]
    recurring_character: Evidenced[bool]
    # Age inference metadata (never derived solely from madeForKids)
    age_confidence: float = 0.0
    classifier_version: str = "heuristic-v2"
    age_evidence_features: List[str] = Field(default_factory=list)
    made_for_kids_fact: Optional[str] = None
    classifier: str = "heuristic"
    classified_at: Optional[datetime] = None

    def low_confidence_fields(self, threshold: float) -> List[str]:
        out: List[str] = []
        for name, field in self.model_dump().items():
            if isinstance(field, dict) and "kind" in field:
                if (
                    field.get("kind") == EvidenceKind.UNKNOWN.value
                    or float(field.get("confidence") or 0) < threshold
                ):
                    out.append(name)
        return out


class NicheKey(BaseModel):
    age: str
    theme: str
    format: str
    language: str = "en"
    character: str = "unknown"

    def label(self) -> str:
        return f"{self.age}|{self.theme}|{self.format}|{self.language}|{self.character}"


class ComponentScores(BaseModel):
    demand: float
    viral: float
    competition: float
    production_complexity: float
    monetization: float
    ip_potential: float
    localization: float


class NicheScore(BaseModel):
    niche: NicheKey
    n_videos: int
    n_channels: int
    median_views_per_day: Optional[float] = None
    p90_views_per_day: Optional[float] = None
    components: ComponentScores
    opportunity_score: Optional[float] = None
    confidence: float
    evidence_status: EvidenceKind
    insufficient_data: bool = False
    max_channel_share: Optional[float] = None
    unknown_rate: Optional[float] = None
    notes: List[str] = Field(default_factory=list)


class ReportBundle(BaseModel):
    generated_at: datetime
    sample_size: int
    evidence_gates_passed: bool
    reports: Dict[str, Any]
    top20: List[NicheScore]
    highlights: Dict[str, Optional[NicheScore]]
    caveats: List[str] = Field(default_factory=list)
    sample_composition: Dict[str, Any] = Field(default_factory=dict)
