"""Build shared-contract sampling windows from validated sensor samples."""

from __future__ import annotations

import hashlib
import statistics
from collections import defaultdict
from datetime import datetime
from typing import Any, Mapping

from .models import (
    SCHEMA_VERSION,
    CollectedWindow,
    RadarTarget,
    SensorHealth,
    SensorHealthReport,
    SensorSample,
    format_utc,
)


def _mean(samples: list[SensorSample], field: str) -> float | None:
    values = [
        float(sample.values[field])
        for sample in samples
        if field in sample.values and sample.values[field] is not None
    ]
    return statistics.fmean(values) if values else None


def _values(samples: list[SensorSample], field: str) -> list[float]:
    return [
        float(sample.values[field])
        for sample in samples
        if field in sample.values and sample.values[field] is not None
    ]


def _relative_summary(values: list[float]) -> dict[str, float | int | None]:
    return {
        "sample_count": len(values),
        "mean": statistics.fmean(values) if values else None,
        "std": statistics.pstdev(values) if len(values) > 1 else (
            0.0 if values else None
        ),
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
    }


def _direct_health(
    reports: Mapping[str, SensorHealthReport],
    sensor: str,
) -> SensorHealth:
    report = reports.get(sensor)
    return report.status if report else SensorHealth.NOT_CONFIGURED


class WindowAccumulator:
    def __init__(
        self,
        *,
        room_id: str,
        device_id: str,
        window_start: datetime,
        window_end: datetime,
        start_monotonic_s: float,
        expected_counts: Mapping[str, int],
    ) -> None:
        self.room_id = room_id
        self.device_id = device_id
        self.window_start = window_start
        self.window_end = window_end
        self.start_monotonic_s = start_monotonic_s
        self.expected_counts = dict(expected_counts)
        self.samples: dict[str, list[SensorSample]] = defaultdict(list)

    def add(self, sample: SensorSample) -> None:
        if sample.valid:
            self.samples[sample.sensor].append(sample)

    def finalize(
        self,
        health_reports: Mapping[str, SensorHealthReport],
        *,
        frames_ref: str | None = None,
    ) -> CollectedWindow:
        thermal_samples = self.samples["thermal"]
        radar_samples = self.samples["radar"]
        sound_samples = self.samples["sound"]
        light_samples = self.samples["light"]
        climate_samples = self.samples["climate"]
        start_token = format_utc(self.window_start, milliseconds=True)
        window_id = f"{self.room_id}-{start_token.replace(':', '').replace('-', '')}"
        target_namespace = hashlib.sha256(window_id.encode("ascii")).hexdigest()[:8]

        thermal: dict[str, Any] = {
            "health": _direct_health(health_reports, "thermal").value,
            "frame_count": len(thermal_samples),
        }
        if frames_ref is not None:
            thermal["frames_ref"] = frames_ref

        tracks: list[dict[str, Any]] = []
        for sample in radar_samples:
            targets = sample.values.get("targets", ())
            tracks.append(
                {
                    "sample_offset_ms": max(
                        0,
                        round((sample.monotonic_s - self.start_monotonic_s) * 1000),
                    ),
                    "targets": [
                        target.to_dict(
                            anonymous_id=(
                                f"target-{target_namespace}-{target.slot + 1}"
                            )
                        )
                        for target in targets
                        if isinstance(target, RadarTarget) and target.valid
                    ],
                }
            )

        rms_values = [float(sample.values["rms"]) for sample in sound_samples]
        sound = {
            "health": _direct_health(health_reports, "sound").value,
            "rms_mean": statistics.fmean(rms_values) if rms_values else None,
            "rms_std": statistics.pstdev(rms_values) if len(rms_values) > 1 else (
                0.0 if rms_values else None
            ),
            "peak": max(
                (float(sample.values["peak"]) for sample in sound_samples),
                default=None,
            ),
        }

        expected_total = sum(self.expected_counts.values())
        valid_total = sum(
            min(len(self.samples[name]), expected)
            for name, expected in self.expected_counts.items()
        )
        completeness = (
            min(1.0, valid_total / expected_total) if expected_total else 1.0
        )
        warnings: list[str] = []
        warnings.extend(
            warning
            for sample in light_samples
            if isinstance((warning := sample.values.get("warning")), str)
        )
        for name, expected in self.expected_counts.items():
            actual = len(self.samples[name])
            if actual < expected:
                warnings.append(f"{name}:received_{actual}_of_{expected}")
            status = _direct_health(health_reports, name)
            if status is not SensorHealth.OK:
                warnings.append(f"{name}:{status.value}")
        thermal_health = _direct_health(health_reports, "thermal")
        radar_health = _direct_health(health_reports, "radar")
        if thermal_health is SensorHealth.OFFLINE:
            if radar_health is SensorHealth.OFFLINE:
                warnings.append("not_inference_ready:thermal_and_radar_offline")
            elif radar_health is SensorHealth.NOT_CONFIGURED:
                warnings.append(
                    "not_inference_ready:thermal_offline_without_radar"
                )

        payload = {
            "schema_version": SCHEMA_VERSION,
            "window_id": window_id,
            "room_id": self.room_id,
            "device_id": self.device_id,
            "window_start": format_utc(self.window_start),
            "window_end": format_utc(self.window_end),
            "thermal": thermal,
            "radar": {
                "health": _direct_health(health_reports, "radar").value,
                "sample_count": len(radar_samples),
                "tracks": tracks,
            },
            "sound": sound,
            "environment": {
                "light_lux": _mean(light_samples, "light_lux"),
                "temperature_c": _mean(climate_samples, "temperature_c"),
                "humidity_pct": _mean(climate_samples, "humidity_pct"),
            },
            "quality": {
                "completeness": round(completeness, 6),
                "warnings": sorted(set(warnings)),
            },
        }
        thermal_frames = tuple(
            tuple(float(value) for value in sample.values["temperatures_c"])
            for sample in thermal_samples
        )
        light_adc = _values(light_samples, "light_adc_raw")
        light_normalized = _values(light_samples, "light_normalized")
        sound_sensor_model = next(
            (
                str(sample.values["sensor_model"])
                for sample in sound_samples
                if sample.values.get("sensor_model")
            ),
            "HW-485",
        )
        relative_features = {
            "schema_version": SCHEMA_VERSION,
            "window_id": window_id,
            "light": {
                "sensor_model": "HW-486",
                "calibrated_lux": any(
                    bool(sample.values.get("calibrated_lux"))
                    for sample in light_samples
                ),
                "adc": _relative_summary(light_adc),
                "normalized": _relative_summary(light_normalized),
            },
            "sound": {
                "sensor_model": sound_sensor_model,
                "calibrated_db": any(
                    bool(sample.values.get("calibrated_db"))
                    for sample in sound_samples
                ),
                "rms": _relative_summary(rms_values),
                "peak": max(
                    (float(sample.values["peak"]) for sample in sound_samples),
                    default=None,
                ),
            },
        }
        return CollectedWindow(
            payload=payload,
            thermal_frames=thermal_frames,
            health_reports=dict(health_reports),
            relative_features=relative_features,
        )
