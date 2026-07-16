from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy.orm import Session

from ..models import Forecast, Observation
from ..repositories import ForecastRepository, ObservationRepository
from ..schemas import ForecastResult
from .history import OCCUPANCY_TO_NUMBER, number_to_occupancy


class ForecastStrategy(Protocol):
    def predict(self, session: Session, room_id: str, horizon_minutes: int, now: datetime) -> ForecastResult: ...


class DeterministicForecastStrategy:
    model_version = "deterministic-v1"

    def __init__(self, stale_after_seconds: int) -> None:
        self.stale_after_seconds = stale_after_seconds

    def predict(self, session: Session, room_id: str, horizon_minutes: int, now: datetime) -> ForecastResult:
        repository = ObservationRepository(session)
        target = now + timedelta(minutes=horizon_minutes)
        recent_start = now - timedelta(minutes=60)
        recent = [row for row in repository.before_for_room(room_id, now, recent_start) if row.occupancy_level in OCCUPANCY_TO_NUMBER]
        method = "unknown"
        fallback_reason: str | None = None
        confidence = 0.0
        inputs: list[Observation] = []
        value: float | None = None

        if len(recent) >= 3:
            inputs = recent
            weights = [math.exp(-math.log(2) * max(0, (now - row.observed_at).total_seconds()) / 900) for row in recent]
            value = sum(OCCUPANCY_TO_NUMBER[row.occupancy_level] * weight for row, weight in zip(recent, weights)) / sum(weights)
            confidence = min(0.85, 0.45 + 0.05 * len(recent))
            method = "recent_exponential_average"
        else:
            history_start = now - timedelta(days=30)
            all_history = repository.before_for_room(room_id, now, history_start)
            slot = [
                row
                for row in all_history
                if row.occupancy_level in OCCUPANCY_TO_NUMBER
                and row.observed_at.date() < now.date()
                and row.observed_at.weekday() == target.weekday()
                and abs((row.observed_at.hour * 60 + row.observed_at.minute) - (target.hour * 60 + target.minute)) <= 15
            ]
            if len(slot) >= 3:
                inputs = slot
                value = sum(OCCUPANCY_TO_NUMBER[row.occupancy_level] for row in slot) / len(slot)
                confidence = min(0.75, 0.35 + 0.05 * len(slot))
                method = "same_weekday_time_slot"
                fallback_reason = "INSUFFICIENT_RECENT_DATA"
            else:
                latest_valid = next((row for row in reversed(all_history) if row.occupancy_level in OCCUPANCY_TO_NUMBER), None)
            if len(slot) < 3 and latest_valid is not None:
                inputs = [latest_valid]
                value = float(OCCUPANCY_TO_NUMBER[latest_valid.occupancy_level])
                fresh = (now - latest_valid.observed_at).total_seconds() <= self.stale_after_seconds
                confidence = 0.30 if fresh else 0.15
                method = "current_persistence"
                fallback_reason = "CURRENT_ONLY"
            elif len(slot) < 3:
                fallback_reason = "NO_VALID_DATA"

        if inputs and (now - inputs[-1].observed_at).total_seconds() > self.stale_after_seconds and method != "current_persistence":
            confidence *= 0.5

        result = ForecastResult(
            room_id=room_id,
            generated_at=now,
            target_at=target,
            horizon_minutes=horizon_minutes,
            predicted_occupancy_level=number_to_occupancy(value),
            confidence=round(confidence, 4),
            method=method,
            model_version=self.model_version,
            input_start_at=inputs[0].observed_at if inputs else None,
            input_end_at=inputs[-1].observed_at if inputs else None,
            fallback_reason=fallback_reason,
        )
        ForecastRepository(session).add(
            Forecast(
                room_id=room_id,
                generated_at=result.generated_at,
                target_at=result.target_at,
                horizon_minutes=result.horizon_minutes,
                predicted_occupancy_level=str(result.predicted_occupancy_level),
                confidence=result.confidence,
                method=result.method,
                model_version=result.model_version,
                input_start_at=result.input_start_at,
                input_end_at=result.input_end_at,
                fallback_reason=result.fallback_reason,
            )
        )
        return result
