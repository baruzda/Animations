from __future__ import annotations

from enum import Enum


class EpisodeState(str, Enum):
    IDEA = "IDEA"
    SCRIPTING = "SCRIPTING"
    STORYBOARDING = "STORYBOARDING"
    AWAITING_PRODUCTION_APPROVAL = "AWAITING_PRODUCTION_APPROVAL"
    RENDER_QUEUED = "RENDER_QUEUED"
    RENDERING = "RENDERING"
    ASSEMBLING = "ASSEMBLING"
    QC = "QC"
    AWAITING_FINAL_APPROVAL = "AWAITING_FINAL_APPROVAL"
    READY = "READY"
    FAILED = "FAILED"
    PAUSED_BUDGET = "PAUSED_BUDGET"
    REJECTED = "REJECTED"


_ALLOWED: dict[EpisodeState, set[EpisodeState]] = {
    EpisodeState.IDEA: {EpisodeState.SCRIPTING, EpisodeState.REJECTED},
    EpisodeState.SCRIPTING: {EpisodeState.STORYBOARDING, EpisodeState.FAILED, EpisodeState.REJECTED},
    EpisodeState.STORYBOARDING: {
        EpisodeState.AWAITING_PRODUCTION_APPROVAL,
        EpisodeState.FAILED,
        EpisodeState.REJECTED,
    },
    EpisodeState.AWAITING_PRODUCTION_APPROVAL: {
        EpisodeState.RENDER_QUEUED,
        EpisodeState.REJECTED,
    },
    EpisodeState.RENDER_QUEUED: {
        EpisodeState.RENDERING,
        EpisodeState.PAUSED_BUDGET,
        EpisodeState.FAILED,
    },
    EpisodeState.RENDERING: {
        EpisodeState.ASSEMBLING,
        EpisodeState.PAUSED_BUDGET,
        EpisodeState.FAILED,
    },
    EpisodeState.ASSEMBLING: {EpisodeState.QC, EpisodeState.FAILED},
    EpisodeState.QC: {EpisodeState.AWAITING_FINAL_APPROVAL, EpisodeState.FAILED},
    EpisodeState.AWAITING_FINAL_APPROVAL: {EpisodeState.READY, EpisodeState.RENDER_QUEUED, EpisodeState.REJECTED},
    EpisodeState.PAUSED_BUDGET: {EpisodeState.RENDER_QUEUED, EpisodeState.REJECTED},
    EpisodeState.FAILED: {EpisodeState.RENDER_QUEUED, EpisodeState.REJECTED},
    EpisodeState.READY: set(),
    EpisodeState.REJECTED: set(),
}


def can_transition(current: EpisodeState, target: EpisodeState) -> bool:
    return target in _ALLOWED[current]


def require_transition(current: EpisodeState, target: EpisodeState) -> None:
    if not can_transition(current, target):
        raise ValueError(f"invalid episode transition: {current.value} -> {target.value}")
