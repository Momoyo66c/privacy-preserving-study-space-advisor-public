from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..schemas import SoundPreview, SoundPreviewResponse


@dataclass(slots=True)
class CachedSoundPreview:
    preview: SoundPreview
    expires_monotonic: float
    expires_at: datetime


class SoundPreviewCache:
    """Keep only the latest privacy-safe RMS value for each room in memory."""

    def __init__(self) -> None:
        self._items: dict[str, CachedSoundPreview] = {}
        self._lock = threading.Lock()

    def put(
        self,
        preview: SoundPreview,
        now: datetime | None = None,
    ) -> SoundPreviewResponse:
        now = now or datetime.now(timezone.utc)
        ttl = min(10, preview.expires_in_seconds)
        expires_at = now + timedelta(seconds=ttl)
        with self._lock:
            self._items[preview.room_id] = CachedSoundPreview(
                preview,
                time.monotonic() + ttl,
                expires_at,
            )
        return self.get(preview.room_id, now=now)

    def get(
        self,
        room_id: str,
        now: datetime | None = None,
    ) -> SoundPreviewResponse:
        now = now or datetime.now(timezone.utc)
        with self._lock:
            item = self._items.get(room_id)
            if item is None:
                return SoundPreviewResponse(
                    room_id=room_id,
                    available=False,
                    unavailable_reason="not_available",
                )
            if time.monotonic() >= item.expires_monotonic or now >= item.expires_at:
                self._items.pop(room_id, None)
                return SoundPreviewResponse(
                    room_id=room_id,
                    available=False,
                    unavailable_reason="expired",
                )
            return SoundPreviewResponse(
                room_id=room_id,
                available=True,
                captured_at=item.preview.captured_at,
                rms=item.preview.rms,
                expires_at=item.expires_at,
            )
