from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from cartoon_factory.domain.models import CostEvent, Episode
from cartoon_factory.domain.states import EpisodeState


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class BudgetPolicy:
    episode_soft_cap_usd: float = 4.50
    episode_hard_cap_usd: float = 6.00
    scene_retry_limit: int = 2
    max_parallel_video_jobs: int = 3

    def __post_init__(self) -> None:
        if self.episode_soft_cap_usd < 0 or self.episode_hard_cap_usd <= 0:
            raise ValueError("budget caps must be positive")
        if self.episode_soft_cap_usd > self.episode_hard_cap_usd:
            raise ValueError("soft cap must not exceed hard cap")
        if self.scene_retry_limit < 0:
            raise ValueError("scene_retry_limit must be >= 0")
        if self.max_parallel_video_jobs < 1:
            raise ValueError("max_parallel_video_jobs must be >= 1")


class BudgetGuard:
    def __init__(self, policy: Optional[BudgetPolicy] = None) -> None:
        self.policy = policy or BudgetPolicy()

    def reserve(
        self,
        episode: Episode,
        *,
        provider: str,
        operation: str,
        estimated_usd: float,
        scene_index: Optional[int] = None,
    ) -> CostEvent:
        if estimated_usd < 0:
            raise ValueError("estimated_usd must be >= 0")
        projected = episode.spent_cost_usd + estimated_usd
        if projected > self.policy.episode_hard_cap_usd:
            if episode.state in {EpisodeState.RENDER_QUEUED, EpisodeState.RENDERING}:
                episode.state = EpisodeState.PAUSED_BUDGET
            raise BudgetExceeded(
                f"episode {episode.id}: projected ${projected:.2f} exceeds hard cap "
                f"${self.policy.episode_hard_cap_usd:.2f}"
            )
        return CostEvent(
            episode_id=episode.id,
            scene_index=scene_index,
            provider=provider,
            operation=operation,
            estimated_usd=estimated_usd,
        )

    def reconcile(self, episode: Episode, event: CostEvent, actual_usd: float) -> CostEvent:
        if actual_usd < 0:
            raise ValueError("actual_usd must be >= 0")
        event.actual_usd = actual_usd
        event.reserved = False
        episode.spent_cost_usd += actual_usd
        if episode.spent_cost_usd > self.policy.episode_hard_cap_usd:
            episode.state = EpisodeState.PAUSED_BUDGET
            raise BudgetExceeded(
                f"episode {episode.id}: actual spend ${episode.spent_cost_usd:.2f} "
                f"exceeded hard cap ${self.policy.episode_hard_cap_usd:.2f}"
            )
        return event

    def soft_cap_reached(self, episode: Episode) -> bool:
        return episode.spent_cost_usd >= self.policy.episode_soft_cap_usd
