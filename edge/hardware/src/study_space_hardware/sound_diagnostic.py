"""Aggregate-only diagnostics for the HW-485 high-rate sampling windows."""

from __future__ import annotations

import json
import math
import os
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import SensorSample, ensure_utc


DIAGNOSTIC_SCHEMA_VERSION = "1.0"
MINIMUM_DIAGNOSTIC_WINDOWS = 8
_METRIC_NAMES = ("rms", "std", "peak")


def _percentile(values: tuple[float, ...], fraction: float) -> float:
    if not values:
        raise ValueError("cannot calculate a percentile without values")
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _finite_normalized(value: Any, *, field: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
        raise ValueError(f"{field} must be a finite normalized value")
    return numeric


def _positive_integer(value: Any, *, field: str) -> int:
    numeric = int(value)
    if numeric < 1:
        raise ValueError(f"{field} must be positive")
    return numeric


@dataclass(frozen=True, slots=True)
class MetricSummary:
    """Distribution summary that cannot reconstruct individual sound windows."""

    minimum: float
    median: float
    p95: float
    maximum: float
    nonzero_windows: int

    @classmethod
    def from_values(cls, values: Iterable[float]) -> "MetricSummary":
        normalized = tuple(
            _finite_normalized(value, field="metric value") for value in values
        )
        if len(normalized) < MINIMUM_DIAGNOSTIC_WINDOWS:
            raise ValueError(
                "diagnostic metrics require at least "
                f"{MINIMUM_DIAGNOSTIC_WINDOWS} windows"
            )
        return cls(
            minimum=min(normalized),
            median=statistics.median(normalized),
            p95=_percentile(normalized, 0.95),
            maximum=max(normalized),
            nonzero_windows=sum(value > 0.0 for value in normalized),
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MetricSummary":
        expected = {
            "minimum",
            "median",
            "p95",
            "maximum",
            "nonzero_windows",
        }
        if set(value) != expected:
            raise ValueError("diagnostic metric fields do not match the schema")
        summary = cls(
            minimum=_finite_normalized(value["minimum"], field="minimum"),
            median=_finite_normalized(value["median"], field="median"),
            p95=_finite_normalized(value["p95"], field="p95"),
            maximum=_finite_normalized(value["maximum"], field="maximum"),
            nonzero_windows=int(value["nonzero_windows"]),
        )
        if not (
            summary.minimum
            <= summary.median
            <= summary.p95
            <= summary.maximum
        ):
            raise ValueError("diagnostic metric quantiles are not ordered")
        if summary.nonzero_windows < 0:
            raise ValueError("nonzero_windows cannot be negative")
        return summary

    def to_dict(self) -> dict[str, float | int]:
        return {
            "minimum": self.minimum,
            "median": self.median,
            "p95": self.p95,
            "maximum": self.maximum,
            "nonzero_windows": self.nonzero_windows,
        }


@dataclass(frozen=True, slots=True)
class SoundDiagnosticSnapshot:
    """One environment's aggregate-only sound response snapshot."""

    device_id: str
    label: str
    captured_at: str
    window_count: int
    firmware_sample_points: int
    chunk_frames_min: int
    chunk_frames_max: int
    metrics: Mapping[str, MetricSummary]

    @classmethod
    def from_samples(
        cls,
        *,
        device_id: str,
        label: str,
        samples: Iterable[SensorSample],
        captured_at: datetime | None = None,
    ) -> "SoundDiagnosticSnapshot":
        if not device_id or not device_id.isascii():
            raise ValueError("device_id must be a non-empty ASCII string")
        if label not in {"quiet", "reference"}:
            raise ValueError("diagnostic label must be quiet or reference")
        accepted = tuple(samples)
        if len(accepted) < MINIMUM_DIAGNOSTIC_WINDOWS:
            raise ValueError(
                "diagnostic snapshot requires at least "
                f"{MINIMUM_DIAGNOSTIC_WINDOWS} windows"
            )

        metric_values: dict[str, list[float]] = {
            name: [] for name in _METRIC_NAMES
        }
        chunk_frames: list[int] = []
        for sample in accepted:
            if sample.sensor != "sound" or not sample.valid:
                raise ValueError("diagnostic samples must be valid sound samples")
            rms_value = sample.values.get(
                "rms_sensor_normalized",
                sample.values.get("rms"),
            )
            peak_value = sample.values.get(
                "peak_sensor_normalized",
                sample.values.get("peak"),
            )
            values = {
                "rms": rms_value,
                "std": sample.values.get("std"),
                "peak": peak_value,
            }
            for name, value in values.items():
                if value is None:
                    raise ValueError(f"sound sample is missing {name}")
                metric_values[name].append(
                    _finite_normalized(value, field=name)
                )
            chunk_frames.append(
                _positive_integer(
                    sample.values.get("chunk_frames"),
                    field="chunk_frames",
                )
            )

        timestamp = ensure_utc(captured_at or datetime.now(timezone.utc))
        return cls(
            device_id=device_id,
            label=label,
            captured_at=timestamp.isoformat(timespec="seconds").replace(
                "+00:00", "Z"
            ),
            window_count=len(accepted),
            firmware_sample_points=sum(chunk_frames),
            chunk_frames_min=min(chunk_frames),
            chunk_frames_max=max(chunk_frames),
            metrics={
                name: MetricSummary.from_values(values)
                for name, values in metric_values.items()
            },
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SoundDiagnosticSnapshot":
        expected = {
            "schema_version",
            "sensor_model",
            "device_id",
            "label",
            "captured_at",
            "window_count",
            "firmware_sample_points",
            "chunk_frames_min",
            "chunk_frames_max",
            "metrics",
            "raw_audio_persisted",
            "per_window_values_persisted",
        }
        if set(value) != expected:
            raise ValueError("sound diagnostic fields do not match the schema")
        if value["schema_version"] != DIAGNOSTIC_SCHEMA_VERSION:
            raise ValueError("unsupported sound diagnostic schema version")
        if value["sensor_model"] != "HW-485":
            raise ValueError("sound diagnostic sensor model must be HW-485")
        if value["raw_audio_persisted"] is not False:
            raise ValueError("sound diagnostics must not persist raw audio")
        if value["per_window_values_persisted"] is not False:
            raise ValueError(
                "sound diagnostics must not persist per-window values"
            )
        metrics_value = value["metrics"]
        if not isinstance(metrics_value, Mapping):
            raise ValueError("metrics must be an object")
        if set(metrics_value) != set(_METRIC_NAMES):
            raise ValueError("diagnostic metrics must contain rms, std and peak")

        window_count = int(value["window_count"])
        if window_count < MINIMUM_DIAGNOSTIC_WINDOWS:
            raise ValueError("diagnostic window_count is too small")
        snapshot = cls(
            device_id=str(value["device_id"]),
            label=str(value["label"]),
            captured_at=str(value["captured_at"]),
            window_count=window_count,
            firmware_sample_points=_positive_integer(
                value["firmware_sample_points"],
                field="firmware_sample_points",
            ),
            chunk_frames_min=_positive_integer(
                value["chunk_frames_min"],
                field="chunk_frames_min",
            ),
            chunk_frames_max=_positive_integer(
                value["chunk_frames_max"],
                field="chunk_frames_max",
            ),
            metrics={
                name: MetricSummary.from_dict(metrics_value[name])
                for name in _METRIC_NAMES
            },
        )
        if not snapshot.device_id or not snapshot.device_id.isascii():
            raise ValueError("device_id must be a non-empty ASCII string")
        if snapshot.label not in {"quiet", "reference"}:
            raise ValueError("diagnostic label must be quiet or reference")
        if snapshot.chunk_frames_min > snapshot.chunk_frames_max:
            raise ValueError("chunk frame bounds are not ordered")
        if not 0 <= snapshot.firmware_sample_points:
            raise ValueError("firmware_sample_points cannot be negative")
        for metric in snapshot.metrics.values():
            if metric.nonzero_windows > snapshot.window_count:
                raise ValueError("nonzero window count exceeds window_count")
        try:
            parsed_at = datetime.fromisoformat(
                snapshot.captured_at.replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise ValueError("captured_at must be ISO 8601") from exc
        ensure_utc(parsed_at)
        return snapshot

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
            "sensor_model": "HW-485",
            "device_id": self.device_id,
            "label": self.label,
            "captured_at": self.captured_at,
            "window_count": self.window_count,
            "firmware_sample_points": self.firmware_sample_points,
            "chunk_frames_min": self.chunk_frames_min,
            "chunk_frames_max": self.chunk_frames_max,
            "metrics": {
                name: self.metrics[name].to_dict() for name in _METRIC_NAMES
            },
            "raw_audio_persisted": False,
            "per_window_values_persisted": False,
        }


def save_snapshot(path: str | Path, snapshot: SoundDiagnosticSnapshot) -> None:
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if os.name != "nt":
        destination.chmod(0o600)


def load_snapshot(
    path: str | Path,
    *,
    expected_device_id: str | None = None,
    expected_label: str | None = None,
) -> SoundDiagnosticSnapshot:
    source = Path(path).expanduser()
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load sound diagnostic {source}") from exc
    if not isinstance(value, Mapping):
        raise ValueError("sound diagnostic root must be an object")
    snapshot = SoundDiagnosticSnapshot.from_dict(value)
    if expected_device_id is not None and snapshot.device_id != expected_device_id:
        raise ValueError("sound diagnostic belongs to a different device")
    if expected_label is not None and snapshot.label != expected_label:
        raise ValueError("sound diagnostic label does not match")
    return snapshot


def _metric_comparison(
    quiet: MetricSummary,
    reference: MetricSummary,
) -> dict[str, float | bool]:
    sustained_delta = reference.p95 - quiet.p95
    impulse_delta = reference.maximum - quiet.maximum
    sustained_threshold = max(1e-5, quiet.p95 * 0.25)
    impulse_threshold = max(1e-5, quiet.maximum * 0.25)
    return {
        "quiet_p95": quiet.p95,
        "reference_p95": reference.p95,
        "p95_delta": sustained_delta,
        "quiet_max": quiet.maximum,
        "reference_max": reference.maximum,
        "max_delta": impulse_delta,
        "sustained_response": sustained_delta >= sustained_threshold,
        "impulse_response": impulse_delta >= impulse_threshold,
    }


def compare_snapshots(
    quiet: SoundDiagnosticSnapshot,
    reference: SoundDiagnosticSnapshot,
) -> dict[str, Any]:
    if quiet.device_id != reference.device_id:
        raise ValueError("diagnostic snapshots belong to different devices")
    if quiet.label != "quiet" or reference.label != "reference":
        raise ValueError("compare requires quiet then reference snapshots")
    comparisons = {
        name: _metric_comparison(
            quiet.metrics[name],
            reference.metrics[name],
        )
        for name in _METRIC_NAMES
    }
    std_sustained = bool(comparisons["std"]["sustained_response"])
    peak_sustained = bool(comparisons["peak"]["sustained_response"])
    peak_impulse = bool(comparisons["peak"]["impulse_response"])
    rms_sustained = bool(comparisons["rms"]["sustained_response"])
    if std_sustained and peak_sustained:
        conclusion = "sustained_ac_response_detected"
        suitable = True
    elif peak_impulse:
        conclusion = "peak_or_impulse_only_response"
        suitable = False
    elif rms_sustained:
        conclusion = "dc_or_envelope_response_without_ac_variation"
        suitable = False
    else:
        conclusion = "no_reliable_sound_response"
        suitable = False
    return {
        "ok": True,
        "device_id": quiet.device_id,
        "quiet_captured_at": quiet.captured_at,
        "reference_captured_at": reference.captured_at,
        "comparisons": comparisons,
        "conclusion": conclusion,
        "suitable_for_relative_room_noise": suitable,
        "calibrated_db": False,
        "raw_audio_persisted": False,
        "per_window_values_persisted": False,
    }
