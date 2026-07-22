"""Shared in-process models for sensor acquisition.

Only summarized window payloads leave this module. Raw thermal frames are kept
in ``CollectedWindow.thermal_frames`` for optional local NPZ persistence and
are deliberately excluded from ``payload``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping


SCHEMA_VERSION = "1.0"
THERMAL_WIDTH = 32
THERMAL_HEIGHT = 24
THERMAL_PIXELS = THERMAL_WIDTH * THERMAL_HEIGHT


class SensorHealth(StrEnum):
    """Health values fixed by the shared contract."""

    OK = "ok"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    NOT_CONFIGURED = "not_configured"


class SampleQuality(StrEnum):
    """Per-sample quality classification used inside Module 1."""

    VALID = "valid"
    SUSPECT = "suspect"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class SensorSample:
    """One timestamped sensor reading.

    ``values`` contains sensor-specific values, while ``units`` documents each
    numeric field. A sample marked invalid is retained only for diagnostics and
    never contributes to completeness or window aggregates.
    """

    sensor: str
    captured_at: datetime
    monotonic_s: float
    values: Mapping[str, Any]
    units: Mapping[str, str]
    quality: SampleQuality = SampleQuality.VALID
    warnings: tuple[str, ...] = ()
    source: str = "unknown"

    @property
    def valid(self) -> bool:
        return self.quality is not SampleQuality.INVALID


@dataclass(frozen=True, slots=True)
class SensorHealthReport:
    sensor: str
    status: SensorHealth
    successful_reads: int = 0
    failed_reads: int = 0
    consecutive_failures: int = 0
    last_success_at: datetime | None = None
    message: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "sensor": self.sensor,
            "status": self.status.value,
            "successful_reads": self.successful_reads,
            "failed_reads": self.failed_reads,
            "consecutive_failures": self.consecutive_failures,
        }
        if self.last_success_at is not None:
            result["last_success_at"] = format_utc(self.last_success_at)
        if self.message:
            result["message"] = self.message
        if self.details:
            result["details"] = dict(self.details)
        return result


@dataclass(frozen=True, slots=True)
class RadarTarget:
    """Anonymous LD2450 target valid only inside the current sample/window."""

    slot: int
    x_mm: int
    y_mm: int
    speed_cm_s: int
    distance_resolution_mm: int
    valid: bool = True

    def to_dict(self, anonymous_id: str | None = None) -> dict[str, Any]:
        result = {
            "x_mm": self.x_mm,
            "y_mm": self.y_mm,
            "speed_cm_s": self.speed_cm_s,
            "distance_resolution_mm": self.distance_resolution_mm,
            "valid": self.valid,
        }
        if anonymous_id is not None:
            result["target_id"] = anonymous_id
        return result


@dataclass(slots=True)
class CollectedWindow:
    """A contract payload plus local-only raw thermal frames."""

    payload: dict[str, Any]
    thermal_frames: tuple[tuple[float, ...], ...] = ()
    health_reports: Mapping[str, SensorHealthReport] = field(default_factory=dict)
    relative_features: Mapping[str, Any] = field(default_factory=dict)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


def format_utc(value: datetime, *, milliseconds: bool = False) -> str:
    value = ensure_utc(value)
    timespec = "milliseconds" if milliseconds else "seconds"
    return value.isoformat(timespec=timespec).replace("+00:00", "Z")
