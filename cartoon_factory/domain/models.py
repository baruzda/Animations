from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from cartoon_factory.domain.states import EpisodeState, require_transition


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RadarCandidate(BaseModel):
    radar_run_id: str
    generated_at: datetime
    niche_key: str
    opportunity_score: float
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_status: str
    insufficient_data: bool = False
    evidence_gates_passed: bool
    synthetic: bool = False

    def assert_production_safe(self, min_confidence: float = 0.65) -> None:
        reasons: list[str] = []
        if self.synthetic:
            reasons.append("synthetic radar run")
        if not self.evidence_gates_passed:
            reasons.append("evidence gates failed")
        if self.insufficient_data:
            reasons.append("insufficient data")
        if self.confidence < min_confidence:
            reasons.append(f"confidence {self.confidence:.2f} < {min_confidence:.2f}")
        if reasons:
            raise ValueError("candidate is not production-safe: " + "; ".join(reasons))


class SceneScript(BaseModel):
    index: int = Field(ge=1)
    duration_seconds: float = Field(gt=0, le=12)
    location: str = Field(min_length=1)
    character_ids: list[str] = Field(default_factory=list)
    action: str = Field(min_length=1)
    camera: str = Field(min_length=1)
    emotion: str = Field(min_length=1)
    dialogue: str | None = None
    video_prompt: str = Field(min_length=1)
    negative_prompt: str | None = None
    sfx: list[str] = Field(default_factory=list)
    transition: str = "cut"


class EpisodeScript(BaseModel):
    title: str = Field(min_length=1)
    logline: str = Field(min_length=1)
    hook: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    target_duration_seconds: float = Field(gt=0, le=180)
    characters: list[str] = Field(default_factory=list)
    scenes: list[SceneScript] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scene_contract(self) -> EpisodeScript:
        indices = [scene.index for scene in self.scenes]
        if indices != list(range(1, len(indices) + 1)):
            raise ValueError("scene indices must be contiguous and start at 1")
        total = sum(scene.duration_seconds for scene in self.scenes)
        tolerance = max(2.0, self.target_duration_seconds * 0.15)
        if abs(total - self.target_duration_seconds) > tolerance:
            raise ValueError(
                f"scene duration total {total:.1f}s does not match target "
                f"{self.target_duration_seconds:.1f}s within tolerance {tolerance:.1f}s"
            )
        return self


class Episode(BaseModel):
    id: str = Field(default_factory=lambda: f"ep_{uuid4().hex[:12]}")
    idea_id: str | None = None
    state: EpisodeState = EpisodeState.IDEA
    script: EpisodeScript | None = None
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)
    spent_cost_usd: float = Field(default=0.0, ge=0.0)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    def transition(self, target: EpisodeState) -> Episode:
        require_transition(self.state, target)
        self.state = target
        self.updated_at = utcnow()
        return self


class Asset(BaseModel):
    id: str = Field(default_factory=lambda: f"asset_{uuid4().hex[:12]}")
    episode_id: str
    scene_index: int | None = None
    kind: str
    provider: str
    model: str
    storage_uri: str
    checksum: str | None = None
    provider_job_id: str | None = None
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    prompt_version: str | None = None
    cost_usd: float = Field(default=0.0, ge=0.0)
    created_at: datetime = Field(default_factory=utcnow)


class CostEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"cost_{uuid4().hex[:12]}")
    episode_id: str
    scene_index: int | None = None
    provider: str
    operation: str
    estimated_usd: float = Field(ge=0.0)
    actual_usd: float | None = Field(default=None, ge=0.0)
    reserved: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class QCResult(BaseModel):
    episode_id: str
    passed: bool
    code: str
    message: str
    scene_index: int | None = None
    asset_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Approval(BaseModel):
    episode_id: str
    kind: str
    approved: bool
    actor: str = "human"
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("kind")
    @classmethod
    def known_kind(cls, value: str) -> str:
        if value not in {"production", "final"}:
            raise ValueError("approval kind must be production or final")
        return value
