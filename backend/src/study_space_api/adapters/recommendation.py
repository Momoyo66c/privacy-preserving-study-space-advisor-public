from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..schemas import (
    AuthenticatedRecommendationRequest,
    RecommendationItem,
    RecommendationPreferences,
    RecommendationRequest,
    RoomStatus,
)


@dataclass(slots=True)
class RecommendationContext:
    request: RecommendationRequest | AuthenticatedRecommendationRequest
    rooms: list[RoomStatus]
    effective_preferences: RecommendationPreferences | None = None
    preferred_temperature_c: float | None = None

    @property
    def preferences(self) -> RecommendationPreferences:
        if self.effective_preferences is not None:
            return self.effective_preferences
        if isinstance(self.request, RecommendationRequest):
            return self.request.preferences
        raise ValueError("authenticated recommendation context requires effective preferences")


@dataclass(slots=True)
class AdapterResult:
    recommendations: list[RecommendationItem]
    warnings: list[str]
    adapter_name: str
    score_breakdown: dict[str, dict] | None = None


class RecommendationAdapter(Protocol):
    name: str

    async def health(self) -> dict[str, str]: ...

    async def rank(self, context: RecommendationContext) -> AdapterResult: ...
