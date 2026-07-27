from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..schemas import PeopleCountPrediction, PeopleCountPreviewResponse


@dataclass(slots=True)
class CachedPeopleCount:
    prediction: PeopleCountPrediction
    expires_monotonic: float
    expires_at: datetime


class PeopleCountPreviewCache:
    """Keep one short-lived, privacy-safe count prediction per room in memory."""

    def __init__(self, ttl_seconds: int = 30) -> None:
        self._ttl_seconds = max(1, min(30, ttl_seconds))
        self._items: dict[str, CachedPeopleCount] = {}
        self._lock = threading.Lock()

    def put(
        self,
        prediction: PeopleCountPrediction,
        now: datetime | None = None,
    ) -> PeopleCountPreviewResponse:
        now = now or datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self._ttl_seconds)
        with self._lock:
            self._items[prediction.room_id] = CachedPeopleCount(
                prediction=prediction,
                expires_monotonic=time.monotonic() + self._ttl_seconds,
                expires_at=expires_at,
            )
        return self.get(prediction.room_id, now=now)

    def get(
        self,
        room_id: str,
        now: datetime | None = None,
    ) -> PeopleCountPreviewResponse:
        now = now or datetime.now(timezone.utc)
        with self._lock:
            item = self._items.get(room_id)
            if item is None:
                return PeopleCountPreviewResponse(
                    room_id=room_id,
                    available=False,
                    unavailable_reason="not_available",
                )
            if time.monotonic() >= item.expires_monotonic or now >= item.expires_at:
                self._items.pop(room_id, None)
                return PeopleCountPreviewResponse(
                    room_id=room_id,
                    available=False,
                    unavailable_reason="expired",
                )
            prediction = item.prediction
            return PeopleCountPreviewResponse(
                room_id=room_id,
                available=True,
                observed_at=prediction.observed_at,
                predicted_people_count=prediction.predicted_people_count,
                predicted_people_count_rounded=prediction.predicted_people_count_rounded,
                occupancy_level=prediction.occupancy_level,
                confidence=prediction.confidence,
                model=prediction.model,
                warnings=prediction.warnings,
                expires_at=item.expires_at,
            )
