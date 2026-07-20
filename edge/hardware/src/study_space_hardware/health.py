"""Sensor health transitions and counters."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import SensorHealth, SensorHealthReport


class HealthTracker:
    def __init__(
        self,
        sensor: str,
        *,
        offline_threshold: int = 3,
        configured: bool = True,
    ) -> None:
        if offline_threshold < 1:
            raise ValueError("offline_threshold must be at least 1")
        self.sensor = sensor
        self.offline_threshold = offline_threshold
        self.status = (
            SensorHealth.DEGRADED if configured else SensorHealth.NOT_CONFIGURED
        )
        self.successful_reads = 0
        self.failed_reads = 0
        self.consecutive_failures = 0
        self.last_success_at: datetime | None = None
        self.message: str | None = None
        self.details: dict[str, Any] = {}

    def mark_started(self) -> None:
        if self.status is not SensorHealth.NOT_CONFIGURED:
            self.status = SensorHealth.DEGRADED
            self.message = "started; waiting for first valid sample"

    def record_success(
        self,
        captured_at: datetime,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.successful_reads += 1
        self.consecutive_failures = 0
        self.last_success_at = captured_at
        self.status = SensorHealth.OK
        self.message = None
        if details:
            self.details.update(details)

    def record_failure(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.failed_reads += 1
        self.consecutive_failures += 1
        self.status = (
            SensorHealth.OFFLINE
            if self.consecutive_failures >= self.offline_threshold
            else SensorHealth.DEGRADED
        )
        self.message = message
        if details:
            self.details.update(details)

    def mark_offline(self, message: str) -> None:
        self.status = SensorHealth.OFFLINE
        self.message = message

    def report(self) -> SensorHealthReport:
        return SensorHealthReport(
            sensor=self.sensor,
            status=self.status,
            successful_reads=self.successful_reads,
            failed_reads=self.failed_reads,
            consecutive_failures=self.consecutive_failures,
            last_success_at=self.last_success_at,
            message=self.message,
            details=dict(self.details),
        )
