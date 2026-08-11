from __future__ import annotations

from enum import Enum
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field


class EvidenceKind(str, Enum):
    FACT = "FACT"
    INFERENCE = "INFERENCE"
    UNKNOWN = "UNKNOWN"


T = TypeVar("T")


class Evidenced(BaseModel, Generic[T]):
    """Value wrapped with explicit epistemic status."""

    value: Optional[T] = None
    kind: EvidenceKind
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: Optional[str] = None
    rationale: Optional[str] = None

    @classmethod
    def fact(cls, value: T, source: str, confidence: float = 1.0) -> "Evidenced[T]":
        return cls(value=value, kind=EvidenceKind.FACT, confidence=confidence, source=source)

    @classmethod
    def inference(
        cls,
        value: T,
        confidence: float,
        source: str,
        rationale: Optional[str] = None,
    ) -> "Evidenced[T]":
        return cls(
            value=value,
            kind=EvidenceKind.INFERENCE,
            confidence=confidence,
            source=source,
            rationale=rationale,
        )

    @classmethod
    def unknown(
        cls, rationale: Optional[str] = None, source: Optional[str] = None
    ) -> "Evidenced[T]":
        return cls(
            value=None,
            kind=EvidenceKind.UNKNOWN,
            confidence=0.0,
            source=source,
            rationale=rationale or "insufficient evidence",
        )

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump()
