"""Multi-sensor scheduling and non-overlapping window collection."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Mapping

from .actuation.base import StatusIndicator
from .clock import Clock, SystemClock
from .drivers.base import SensorDriver, SensorError
from .models import CollectedWindow, SensorHealthReport
from .windowing import WindowAccumulator


LOGGER = logging.getLogger(__name__)


class SensorOrchestrator:
    def __init__(
        self,
        *,
        room_id: str,
        device_id: str,
        window_seconds: float,
        drivers: Mapping[str, SensorDriver],
        clock: Clock | None = None,
        status_indicator: StatusIndicator | None = None,
    ) -> None:
        if not 5.0 <= window_seconds <= 10.0:
            raise ValueError("window_seconds must be between 5 and 10")
        self.room_id = room_id
        self.device_id = device_id
        self.window_seconds = float(window_seconds)
        self.drivers = dict(drivers)
        self.clock = clock or SystemClock()
        self.status_indicator = status_indicator
        self._running: set[str] = set()

    def start(self) -> None:
        for name, driver in self.drivers.items():
            try:
                driver.start()
                self._running.add(name)
            except SensorError as exc:
                LOGGER.warning(
                    "sensor_start_failed sensor=%s error_type=%s",
                    name,
                    type(exc).__name__,
                )

    def run_window(self) -> CollectedWindow:
        # ``start`` is idempotent for healthy drivers and retries any driver
        # that failed to initialize during an earlier window.
        self.start()
        start_mono = self.clock.monotonic()
        start_utc = self.clock.now_utc()
        end_mono = start_mono + self.window_seconds
        end_utc = start_utc + timedelta(seconds=self.window_seconds)
        expected_counts = {
            name: max(1, round(driver.sample_rate_hz * self.window_seconds))
            for name, driver in self.drivers.items()
        }
        accumulator = WindowAccumulator(
            room_id=self.room_id,
            device_id=self.device_id,
            window_start=start_utc,
            window_end=end_utc,
            start_monotonic_s=start_mono,
            expected_counts=expected_counts,
        )
        next_due = {name: start_mono for name in self._running}

        while self.clock.monotonic() < end_mono:
            now = self.clock.monotonic()
            due_names = [
                name
                for name, due_at in next_due.items()
                if due_at <= now + 1e-9 and due_at < end_mono - 1e-9
            ]
            for name in due_names:
                driver = self.drivers[name]
                sample_available = getattr(driver, "sample_available", None)
                if callable(sample_available) and not sample_available():
                    # ESP32 Hub adapters share a background reader.  Waiting
                    # on one empty logical queue would starve other queues
                    # that already contain timestamped frames.
                    continue
                try:
                    accumulator.add(driver.read())
                except SensorError as exc:
                    LOGGER.warning(
                        "sensor_read_failed sensor=%s error_type=%s",
                        name,
                        type(exc).__name__,
                    )
                interval = 1.0 / driver.sample_rate_hz
                next_due[name] = next_due[name] + interval
                if next_due[name] <= self.clock.monotonic():
                    next_due[name] = self.clock.monotonic() + interval

            if self.clock.monotonic() >= end_mono:
                break
            wake_at = min([end_mono, *next_due.values()]) if next_due else end_mono
            self.clock.sleep(max(0.0005, wake_at - self.clock.monotonic()))

        reports = {
            name: driver.health()
            for name, driver in self.drivers.items()
        }
        return accumulator.finalize(reports)

    def health(self) -> dict[str, SensorHealthReport]:
        return {name: driver.health() for name, driver in self.drivers.items()}

    def apply_room_state(self, room_state: str) -> None:
        if self.status_indicator is None:
            return
        try:
            self.status_indicator.set_state(room_state)
        except Exception:
            LOGGER.exception(
                "status_indicator_update_failed room_state=%s",
                room_state,
            )

    def close(self) -> None:
        for name, driver in self.drivers.items():
            try:
                driver.close()
            except Exception:
                LOGGER.exception("sensor_close_failed sensor=%s", name)
        self._running.clear()
        if self.status_indicator is not None:
            try:
                self.status_indicator.close()
            except Exception:
                LOGGER.exception("status_indicator_close_failed")

    def __enter__(self) -> SensorOrchestrator:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
