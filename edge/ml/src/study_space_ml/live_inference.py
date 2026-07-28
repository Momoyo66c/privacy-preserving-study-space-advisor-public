"""Privacy-safe online people counting and room-state fusion.

Raw MLX90640 frames are accepted only as an in-process argument. The returned
payload contains a short-lived count and the bounded EdgeObservation summary;
it never contains a thermal array, sound waveform, or identity.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy import ndimage

from .predictor import PeopleCountPredictor


FUSION_MODEL_NAME = "module2-live-sensor-fusion"
FUSION_MODEL_VERSION = "1.0.0"
FUSION_FEATURE_SCHEMA_VERSION = "live-fusion.v1"
LIVE_EMPTY_THRESHOLD = 0.80
THERMAL_PRESENCE_HEAT_DELTA_C = 3.20
ZERO_PERSON_FOREGROUND_SCORE = 0.35
LOGGER = logging.getLogger(__name__)


class ThermalForegroundCounter:
    """Estimate zero-to-four people from warm foreground mass.

    A one-shot command file can label a short zero-, one-, or two-person
    calibration. Only aggregate foreground area and excess heat are persisted;
    raw thermal frames never leave this object.
    """

    def __init__(
        self,
        *,
        temperature_delta_c: float = 0.60,
        minimum_pixels: int = 3,
        background_alpha: float = 0.04,
        maximum_people: int = 4,
        stability_windows: int = 2,
        calibration_sample_windows: int = 2,
        calibration_profile_path: str | Path | None = None,
        calibration_command_path: str | Path | None = None,
    ) -> None:
        self.temperature_delta_c = temperature_delta_c
        self.minimum_pixels = minimum_pixels
        self.background_alpha = background_alpha
        self.maximum_people = maximum_people
        self.stability_windows = stability_windows
        self.calibration_sample_windows = calibration_sample_windows
        self.calibration_profile_path = (
            Path(calibration_profile_path).expanduser()
            if calibration_profile_path is not None
            else None
        )
        self.calibration_command_path = (
            Path(calibration_command_path).expanduser()
            if calibration_command_path is not None
            else None
        )
        self._background: np.ndarray | None = None
        self._calibrations: dict[int, tuple[float, float]] = {}
        self._calibration_target: int | None = None
        self._calibration_samples: list[tuple[float, float]] = []
        self._calibration_required_samples = calibration_sample_windows
        self._stable_count = 0
        self._pending_count: int | None = None
        self._pending_windows = 0
        self.last_diagnostics: dict[str, Any] = {}
        self._load_calibration_profile()

    @property
    def calibrated_counts(self) -> tuple[int, ...]:
        return tuple(sorted(self._calibrations))

    def _load_calibration_profile(self) -> None:
        path = self.calibration_profile_path
        if path is None or not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != "thermal-count-calibration.v1":
                raise ValueError("unsupported calibration schema")
            calibrations = payload.get("calibrations") or {}
            for raw_count, values in calibrations.items():
                count = int(raw_count)
                area = float(values["foreground_area"])
                heat = float(values["excess_heat"])
                if 1 <= count <= self.maximum_people and area > 0 and heat > 0:
                    self._calibrations[count] = (area, heat)
        except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
            LOGGER.warning("thermal_count_calibration_profile_ignored path=%s", path)

    def _save_calibration_profile(self) -> None:
        path = self.calibration_profile_path
        if path is None:
            return
        payload = {
            "schema_version": "thermal-count-calibration.v1",
            "calibrations": {
                str(count): {
                    "foreground_area": round(values[0], 3),
                    "excess_heat": round(values[1], 3),
                }
                for count, values in sorted(self._calibrations.items())
            },
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(f"{path.suffix}.tmp")
            temporary.write_text(
                json.dumps(payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError:
            LOGGER.exception("thermal_count_calibration_profile_write_failed path=%s", path)

    def _poll_calibration_command(self) -> None:
        path = self.calibration_command_path
        if path is None or not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            target = int(payload["people_count"])
            samples = int(
                payload.get("sample_windows", self.calibration_sample_windows)
            )
            if not 0 <= target <= self.maximum_people:
                raise ValueError("people_count is outside supported range")
            if not 1 <= samples <= 6:
                raise ValueError("sample_windows is outside supported range")
            self._calibration_target = target
            self._calibration_samples = []
            self._calibration_required_samples = samples
            LOGGER.info(
                "thermal_count_calibration_started people_count=%s sample_windows=%s",
                target,
                samples,
            )
        except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
            LOGGER.warning("thermal_count_calibration_command_ignored path=%s", path)
        finally:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                LOGGER.warning(
                    "thermal_count_calibration_command_remove_failed path=%s",
                    path,
                )

    def _complete_calibration_if_ready(
        self,
        *,
        current: np.ndarray,
        foreground_area: float,
        excess_heat: float,
    ) -> int | None:
        target = self._calibration_target
        if target is None:
            return None
        if target == 0:
            self._background = current.copy()
            self._stable_count = 0
            self._pending_count = None
            self._pending_windows = 0
            self._calibration_target = None
            LOGGER.info("thermal_count_calibration_completed people_count=0")
            return 0
        if foreground_area <= 0 or excess_heat <= 0:
            return 0
        self._calibration_samples.append((foreground_area, excess_heat))
        if len(self._calibration_samples) < self._calibration_required_samples:
            return target
        values = np.asarray(self._calibration_samples, dtype=float)
        aggregate = tuple(float(value) for value in np.median(values, axis=0))
        self._calibrations[target] = aggregate
        self._calibration_target = None
        self._calibration_samples = []
        self._save_calibration_profile()
        self._stable_count = target
        self._pending_count = None
        self._pending_windows = 0
        LOGGER.info(
            "thermal_count_calibration_completed people_count=%s "
            "foreground_area=%.1f excess_heat=%.1f",
            target,
            aggregate[0],
            aggregate[1],
        )
        return target

    @staticmethod
    def _interpolate_metric(
        count: int,
        known: Mapping[int, float],
    ) -> float:
        if count in known:
            return known[count]
        points = sorted((key, value) for key, value in known.items() if key > 0)
        if not points:
            return 0.0
        if len(points) == 1:
            known_count, value = points[0]
            return value * count / known_count
        for (left_count, left), (right_count, right) in zip(points, points[1:]):
            if left_count < count < right_count:
                fraction = (count - left_count) / (right_count - left_count)
                return left + fraction * (right - left)
        if count < points[0][0]:
            known_count, value = points[0]
            return value * count / known_count
        previous_count, previous = points[-2]
        last_count, last = points[-1]
        step = (last - previous) / (last_count - previous_count)
        minimum_step = max(last / last_count * 0.20, 1.0)
        return last + (count - last_count) * max(step, minimum_step)

    def _estimate_calibrated_count(
        self,
        *,
        region_count: int,
        foreground_area: float,
        excess_heat: float,
    ) -> int:
        if foreground_area <= 0 or excess_heat <= 0:
            return 0
        if not self._calibrations:
            return min(max(region_count, 1), self.maximum_people)

        areas = {count: values[0] for count, values in self._calibrations.items()}
        heats = {count: values[1] for count, values in self._calibrations.items()}
        one_area = max(self._interpolate_metric(1, areas), 1.0)
        one_heat = max(self._interpolate_metric(1, heats), 1.0)
        foreground_score = (
            0.55 * foreground_area / one_area
            + 0.45 * excess_heat / one_heat
        )
        if foreground_score < ZERO_PERSON_FOREGROUND_SCORE:
            return 0
        best_count = 1
        best_distance = float("inf")
        for count in range(1, self.maximum_people + 1):
            expected_area = self._interpolate_metric(count, areas)
            expected_heat = self._interpolate_metric(count, heats)
            distance = (
                0.55 * abs(foreground_area - expected_area) / one_area
                + 0.35 * abs(excess_heat - expected_heat) / one_heat
                + 0.10 * abs(region_count - min(region_count, count))
            )
            if distance < best_distance:
                best_count = count
                best_distance = distance
        return best_count

    def _stabilize(self, estimate: int) -> int:
        estimate = min(max(estimate, 0), self.maximum_people)
        if self.stability_windows <= 1 or estimate == self._stable_count:
            self._stable_count = estimate
            self._pending_count = None
            self._pending_windows = 0
            return estimate
        if estimate != self._pending_count:
            self._pending_count = estimate
            self._pending_windows = 1
            return self._stable_count
        self._pending_windows += 1
        if self._pending_windows >= self.stability_windows:
            self._stable_count = estimate
            self._pending_count = None
            self._pending_windows = 0
        return self._stable_count

    def observe(self, thermal_frames: Any) -> int | None:
        try:
            frames = np.asarray(thermal_frames, dtype=float)
        except (TypeError, ValueError):
            return None
        if frames.size == 0:
            return None
        if frames.ndim == 2 and frames.shape[1] == 768:
            frames = frames.reshape((-1, 24, 32))
        elif frames.ndim != 3 or frames.shape[1:] != (24, 32):
            return None
        if not np.all(np.isfinite(frames)):
            return None

        current = np.median(frames, axis=0)
        self._poll_calibration_command()
        if self._background is None:
            self._background = current.copy()
            if self._calibration_target == 0:
                self._complete_calibration_if_ready(
                    current=current,
                    foreground_area=0.0,
                    excess_heat=0.0,
                )
            return None

        positive_delta = np.maximum(current - self._background, 0.0)
        foreground = positive_delta >= self.temperature_delta_c
        foreground = ndimage.binary_closing(
            foreground,
            structure=np.ones((3, 3), dtype=bool),
        )
        labels, region_count = ndimage.label(
            foreground,
            structure=np.ones((3, 3), dtype=int),
        )
        valid_foreground = np.zeros_like(foreground, dtype=bool)
        valid_regions = 0
        for region_id in range(1, region_count + 1):
            region = labels == region_id
            if int(np.count_nonzero(region)) >= self.minimum_pixels:
                valid_foreground |= region
                valid_regions += 1

        foreground_area = float(np.count_nonzero(valid_foreground))
        excess_heat = float(
            np.maximum(
                positive_delta[valid_foreground] - self.temperature_delta_c,
                0.0,
            ).sum()
        )
        calibration_count = self._complete_calibration_if_ready(
            current=current,
            foreground_area=foreground_area,
            excess_heat=excess_heat,
        )
        if calibration_count is None:
            raw_estimate = self._estimate_calibrated_count(
                region_count=valid_regions,
                foreground_area=foreground_area,
                excess_heat=excess_heat,
            )
            people_count = self._stabilize(raw_estimate)
        else:
            raw_estimate = calibration_count
            people_count = calibration_count

        if raw_estimate == 0:
            self._background = (
                (1.0 - self.background_alpha) * self._background
                + self.background_alpha * current
            )
        else:
            update = ~foreground
            self._background[update] = (
                (1.0 - self.background_alpha) * self._background[update]
                + self.background_alpha * current[update]
            )
        self.last_diagnostics = {
            "raw_region_count": valid_regions,
            "foreground_area": round(foreground_area, 3),
            "excess_heat": round(excess_heat, 3),
            "raw_estimate": raw_estimate,
            "stable_count": people_count,
            "calibrated_counts": self.calibrated_counts,
            "calibration_target": self._calibration_target,
        }
        return min(people_count, self.maximum_people)


def occupancy_level_for_live_count(people_count: int) -> str:
    if people_count <= 0:
        return "empty"
    if people_count <= 2:
        return "low"
    if people_count == 3:
        return "medium"
    return "high"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _health_value(report: Any, fallback: str = "not_configured") -> str:
    status = getattr(report, "status", None)
    value = getattr(status, "value", status)
    if value in {"ok", "degraded", "offline", "not_configured"}:
        return str(value)
    return fallback


def _environment_health(health_reports: Mapping[str, Any]) -> str:
    light = _health_value(health_reports.get("light"))
    climate = _health_value(health_reports.get("climate"))
    statuses = {light, climate}
    if statuses == {"ok"}:
        return "ok"
    if "offline" in statuses:
        return "offline"
    if statuses == {"not_configured"}:
        return "not_configured"
    return "degraded"


def _stable_observation_id(window_id: str) -> str:
    digest = hashlib.sha256(
        f"{window_id}:{FUSION_MODEL_VERSION}".encode("utf-8")
    ).hexdigest()[:16]
    return f"live-{digest}"


@dataclass(frozen=True, slots=True)
class FusionResult:
    room_state: str
    suitability_score: int
    confidence: float
    warnings: tuple[str, ...]


def fuse_room_state(
    *,
    people_count: int,
    occupancy_level: str,
    count_confidence: float,
    sound_rms: float | None,
    light_relative: float | None,
    temperature_c: float | None,
    humidity_pct: float | None,
    thermal_health: str,
    sound_health: str,
    environment_health: str,
    completeness: float,
) -> FusionResult:
    """Fuse the live count, sound activity, and environmental comfort.

    Count plus sound determine the four-state label. Light, temperature, and
    humidity adjust suitability because the shared state enum has no separate
    comfort label. Missing required inputs produce ``unknown`` rather than a
    fabricated zero.
    """

    warnings: list[str] = []
    if thermal_health != "ok" or count_confidence < 0.25:
        room_state = "unknown"
        state_confidence = 0.0
        warnings.append("LIVE_FUSION_THERMAL_OR_COUNT_INSUFFICIENT")
    elif sound_health not in {"ok", "degraded"} or sound_rms is None:
        room_state = "unknown"
        state_confidence = count_confidence * 0.45
        warnings.append("LIVE_FUSION_SOUND_UNAVAILABLE")
    elif sound_rms >= 0.30 or occupancy_level == "high":
        room_state = "not_recommended_noisy_or_crowded"
        state_confidence = 0.82
    elif people_count <= 0:
        if sound_rms < 0.08:
            room_state = "empty_or_low_activity"
            state_confidence = 0.80
        else:
            room_state = "unknown"
            state_confidence = 0.35
            warnings.append("LIVE_FUSION_COUNT_SOUND_CONFLICT")
    elif sound_rms >= 0.08 or occupancy_level == "medium":
        room_state = "discussion_allowed"
        state_confidence = 0.76
    else:
        room_state = "quiet_study_recommended"
        state_confidence = 0.84

    base_score = {
        "empty_or_low_activity": 78.0,
        "quiet_study_recommended": 88.0,
        "discussion_allowed": 64.0,
        "not_recommended_noisy_or_crowded": 24.0,
        "unknown": 30.0,
    }[room_state]

    score = base_score
    if light_relative is None:
        warnings.append("RELATIVE_LIGHT_UNAVAILABLE")
    elif 0.25 <= light_relative <= 0.90:
        score += 4
    elif light_relative < 0.10:
        score -= 12
    elif light_relative > 0.98:
        score -= 4

    if temperature_c is None or humidity_pct is None:
        warnings.append("CLIMATE_UNAVAILABLE")
    else:
        if 20.0 <= temperature_c <= 26.0:
            score += 3
        else:
            score -= min(12.0, abs(temperature_c - 23.0) * 2.0)
        if 35.0 <= humidity_pct <= 65.0:
            score += 2
        else:
            score -= min(8.0, abs(humidity_pct - 50.0) * 0.35)

    if environment_health != "ok":
        warnings.append("ENVIRONMENT_DEGRADED")
        state_confidence *= 0.92

    confidence = (
        min(count_confidence, state_confidence)
        * _clamp(completeness, 0.45, 1.0)
    )
    if room_state == "unknown":
        score = 30.0
    return FusionResult(
        room_state=room_state,
        suitability_score=int(round(_clamp(score, 0.0, 100.0))),
        confidence=round(_clamp(confidence, 0.0, 0.99), 3),
        warnings=tuple(warnings),
    )


class LiveInferenceProcessor:
    """Convert one completed Module 1 window into two backend write payloads."""

    def __init__(
        self,
        predictor: PeopleCountPredictor,
        *,
        thermal_calibration_profile_path: str | Path | None = None,
        thermal_calibration_command_path: str | Path | None = None,
    ) -> None:
        self.predictor = predictor
        self.thermal_foreground_counter = ThermalForegroundCounter(
            calibration_profile_path=thermal_calibration_profile_path,
            calibration_command_path=thermal_calibration_command_path,
        )

    def __call__(
        self,
        window: Any,
        base_snapshot: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        payload = dict(window.payload)
        relative = dict(window.relative_features)
        internal_count = self.predictor.predict_window(
            payload,
            relative=relative,
            thermal_frames=window.thermal_frames,
            include_features=True,
        )
        model_features = dict(internal_count.get("features") or {})
        LOGGER.debug(
            "live_count_features raw=%.4f rounded=%s heat_delta=%.4f "
            "hot_regions=%.1f hot_area=%.4f motion_path=%.4f sound=%.4f",
            float(internal_count["predicted_people_count"]),
            internal_count["predicted_people_count_rounded"],
            float(model_features.get("thermal_heat_delta_p95_median", 0.0)),
            float(model_features.get("thermal_hot_region_count", 0.0)),
            float(model_features.get("thermal_hot_area_ratio", 0.0)),
            float(model_features.get("thermal_main_hot_centroid_path_px", 0.0)),
            float(model_features.get("sound_rms_mean", 0.0)),
        )
        warnings = [
            str(item)
            for item in internal_count.get("warnings") or []
            if item
        ]
        if float(self.predictor.metadata.get("target_max", 0.0) or 0.0) <= 2.0:
            warnings.append("DEMO_MODEL_TRAINED_FOR_ZERO_TO_TWO_PEOPLE")

        raw_people_count = max(
            0.0,
            float(internal_count["predicted_people_count"]),
        )
        people_count = max(
            0,
            int(internal_count["predicted_people_count_rounded"]),
        )
        thermal_available = bool(
            float(model_features.get("thermal_available", 0.0) or 0.0)
        )
        thermal_heat_delta = float(
            model_features.get("thermal_heat_delta_p95_median", 0.0) or 0.0
        )
        if (
            thermal_available
            and thermal_heat_delta < THERMAL_PRESENCE_HEAT_DELTA_C
            and people_count > 0
        ):
            people_count = 0
            occupancy_level = "empty"
            warnings.append("THERMAL_PRESENCE_GATE_EMPTY")
        elif raw_people_count < LIVE_EMPTY_THRESHOLD and people_count > 0:
            people_count = 0
            occupancy_level = "empty"
            warnings.append("LIVE_EMPTY_DEADBAND_APPLIED")
        else:
            occupancy_level = str(internal_count["occupancy_level"])
        count_confidence = _clamp(
            float(internal_count["confidence"]),
            0.0,
            1.0,
        )
        foreground_people_count = self.thermal_foreground_counter.observe(
            window.thermal_frames
        )
        if foreground_people_count is not None:
            people_count = foreground_people_count
            occupancy_level = occupancy_level_for_live_count(people_count)
            count_confidence = max(count_confidence, 0.65)
            warnings.append("THERMAL_BACKGROUND_COUNT_APPLIED")
        sound = payload.get("sound") or {}
        environment = payload.get("environment") or {}
        relative_sound = (relative.get("sound") or {}).get("rms") or {}
        relative_light = (relative.get("light") or {}).get("normalized") or {}
        sound_rms = _number(
            sound.get("rms_mean", relative_sound.get("mean"))
        )
        sound_peak = _number(
            sound.get("peak", (relative.get("sound") or {}).get("peak"))
        )
        light_relative = _number(relative_light.get("mean"))
        temperature_c = _number(environment.get("temperature_c"))
        humidity_pct = _number(environment.get("humidity_pct"))
        reports = dict(window.health_reports)
        thermal_health = _health_value(
            reports.get("thermal"),
            str((payload.get("thermal") or {}).get("health") or "not_configured"),
        )
        sound_health = _health_value(
            reports.get("sound"),
            str(sound.get("health") or "not_configured"),
        )
        environment_health = _environment_health(reports)
        completeness = float(
            (payload.get("quality") or {}).get("completeness") or 0.0
        )

        fusion = fuse_room_state(
            people_count=people_count,
            occupancy_level=occupancy_level,
            count_confidence=count_confidence,
            sound_rms=sound_rms,
            light_relative=light_relative,
            temperature_c=temperature_c,
            humidity_pct=humidity_pct,
            thermal_health=thermal_health,
            sound_health=sound_health,
            environment_health=environment_health,
            completeness=completeness,
        )
        for item in fusion.warnings:
            if item not in warnings:
                warnings.append(item)
        for item in (payload.get("quality") or {}).get("warnings") or []:
            warning = f"INPUT_WARNING:{item}"
            if warning not in warnings:
                warnings.append(warning)

        count_payload = {
            "schema_version": "people_count_prediction.v1",
            "prediction_id": internal_count["prediction_id"],
            "window_id": payload["window_id"],
            "room_id": payload["room_id"],
            "device_id": payload["device_id"],
            "observed_at": payload["window_end"],
            "predicted_people_count": round(
                raw_people_count,
                4,
            ),
            "predicted_people_count_rounded": people_count,
            "occupancy_level": occupancy_level,
            "confidence": round(count_confidence, 3),
            "model": internal_count["model"],
            "warnings": warnings[:32],
        }

        observation = {
            "schema_version": "1.0",
            "observation_id": _stable_observation_id(str(payload["window_id"])),
            "room_id": payload["room_id"],
            "device_id": payload["device_id"],
            "observed_at": payload["window_end"],
            "window_seconds": max(
                5,
                min(
                    10,
                    int(round(float(model_features.get("window_seconds_actual") or 5))),
                ),
            ),
            "room_state": fusion.room_state,
            "occupancy_level": occupancy_level,
            "suitability_score": fusion.suitability_score,
            "confidence": fusion.confidence,
            "features": {
                "thermal_hot_region_count": int(
                    max(0, round(float(model_features["thermal_hot_region_count"])))
                )
                if model_features.get("thermal_available")
                else None,
                "radar_active_target_count": None,
                "sound_rms_mean": _clamp(sound_rms, 0.0, 1.0)
                if sound_rms is not None
                else None,
                "sound_peak_max": _clamp(sound_peak, 0.0, 1.0)
                if sound_peak is not None
                else None,
                "light_relative_mean": _clamp(light_relative, 0.0, 1.0)
                if light_relative is not None
                else None,
                "light_lux": _number(environment.get("light_lux")),
                "temperature_c": temperature_c,
                "humidity_pct": humidity_pct,
            },
            "sensor_health": {
                "thermal": thermal_health,
                "radar": _health_value(reports.get("radar")),
                "sound": sound_health,
                "environment": environment_health,
            },
            "model": {
                "name": FUSION_MODEL_NAME,
                "version": FUSION_MODEL_VERSION,
                "feature_schema_version": FUSION_FEATURE_SCHEMA_VERSION,
            },
            "warnings": warnings[:32],
        }

        result = dict(base_snapshot)
        result["people_count"] = count_payload
        result["observation"] = observation
        return result
