from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..schemas import RecommendationItem, RecommendationRequest, RoomStatus


@dataclass(slots=True)
class RecommendationContext:
    request: RecommendationRequest
    rooms: list[RoomStatus]


@dataclass(slots=True)
class AdapterResult:
    recommendations: list[RecommendationItem]
    warnings: list[str]
    adapter_name: str


class RecommendationAdapter(Protocol):
    name: str

    async def health(self) -> dict[str, str]: ...

    async def rank(self, context: RecommendationContext) -> AdapterResult: ...
