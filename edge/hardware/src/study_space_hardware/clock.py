"""Clock abstractions keep timing deterministic in tests and simulation."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Protocol


class Clock(Protocol):
    def now_utc(self) -> datetime: ...

    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


class ManualClock:
    """Clock that advances instantly when ``sleep`` is called."""

    def __init__(
        self,
        start: datetime | None = None,
        monotonic_start: float = 0.0,
    ) -> None:
        self._now = start or datetime(2026, 7, 16, tzinfo=timezone.utc)
        if self._now.tzinfo is None:
            raise ValueError("start must be timezone-aware")
        self._monotonic = float(monotonic_start)

    def now_utc(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._monotonic

    def sleep(self, seconds: float) -> None:
        self.advance(seconds)

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("cannot move a clock backwards")
        self._monotonic += seconds
        self._now += timedelta(seconds=seconds)
