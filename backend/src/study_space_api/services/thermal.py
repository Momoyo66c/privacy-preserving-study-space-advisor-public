from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..schemas import ThermalPreview, ThermalPreviewResponse


@dataclass(slots=True)
class CachedPreview:
    preview: ThermalPreview
    expires_monotonic: float
    expires_at: datetime


class ThermalPreviewCache:
    def __init__(self) -> None:
        self._items: dict[str, CachedPreview] = {}
        self._lock = threading.Lock()

    def put(self, preview: ThermalPreview, now: datetime | None = None) -> ThermalPreviewResponse:
        now = now or datetime.now(timezone.utc)
        ttl = min(30, preview.expires_in_seconds)
        expires_at = now + timedelta(seconds=ttl)
        with self._lock:
            self._items[preview.room_id] = CachedPreview(preview, time.monotonic() + ttl, expires_at)
        return self.get(preview.room_id, now=now)

    def get(self, room_id: str, now: datetime | None = None) -> ThermalPreviewResponse:
        now = now or datetime.now(timezone.utc)
        with self._lock:
            item = self._items.get(room_id)
            if item is None:
                return ThermalPreviewResponse(room_id=room_id, available=False, unavailable_reason="not_available")
            if time.monotonic() >= item.expires_monotonic or now >= item.expires_at:
                self._items.pop(room_id, None)
                return ThermalPreviewResponse(room_id=room_id, available=False, unavailable_reason="expired")
            preview = item.preview
            return ThermalPreviewResponse(
                room_id=room_id,
                available=True,
                captured_at=preview.captured_at,
                width=preview.width,
                height=preview.height,
                values=preview.values,
                normalization=preview.normalization,
                expires_at=item.expires_at,
            )
