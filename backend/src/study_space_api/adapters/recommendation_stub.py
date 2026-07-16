from __future__ import annotations

from .recommendation import AdapterResult, RecommendationContext
from ..schemas import RecommendationItem


class StubRecommendationAdapter:
    name = "module3-deterministic-stub"

    async def health(self) -> dict[str, str]:
        return {"status": "degraded", "name": self.name, "mode": "stub"}

    async def rank(self, context: RecommendationContext) -> AdapterResult:
        ranked = sorted(
            context.rooms,
            key=lambda room: (-max(0, (room.suitability_score or 0) - (25 if room.is_stale else 0)), room.room_id),
        )
        items: list[RecommendationItem] = []
        for rank, room in enumerate(ranked, start=1):
            score = max(0, (room.suitability_score or 0) - (25 if room.is_stale else 0))
            forecast = next((item for item in room.forecasts if item.horizon_minutes == 30), None)
            reasons = ["Stub ranking uses current suitability only"]
            if room.is_stale:
                reasons.append("Current data is stale")
            items.append(
                RecommendationItem(
                    room_id=room.room_id,
                    rank=rank,
                    score=score,
                    current_state=room.room_state,
                    occupancy_level=room.occupancy_level,
                    forecast_30m=forecast.predicted_occupancy_level if forecast else "unknown",
                    confidence=room.confidence or 0,
                    is_stale=room.is_stale,
                    reasons=reasons,
                    explanation="Stub recommendation; module 4 will provide final ranking.",
                    explanation_source="stub",
                )
            )
        return AdapterResult(items, ["RECOMMENDATION_STUB_ACTIVE"], self.name)
