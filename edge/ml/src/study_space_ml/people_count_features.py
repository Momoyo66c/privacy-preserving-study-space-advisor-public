from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import ndimage

from .constants import PEOPLE_COUNT_FEATURE_NAMES


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, float) and math.isnan(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _health_available(health: str | None) -> float:
    return 1.0 if health == "ok" else 0.0


def _is_degraded(health: str | None) -> float:
    return 1.0 if health == "degraded" else 0.0


def _is_unavailable(health: str | None) -> float:
    return 1.0 if health in {"offline", "not_configured", None, ""} else 0.0


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def resolve_frames_ref(session_dir: str | Path | None, frames_ref: str | None) -> Path | None:
    if not frames_ref or not session_dir:
        return None

    session_dir = Path(session_dir)
    if frames_ref.startswith("local://"):
        rel = frames_ref.replace("local://", "", 1)
    else:
        rel = frames_ref

    parts = Path(rel).parts
    candidates: list[Path] = []

    # local://session-id/thermal/file.npz
    if parts and parts[0] == session_dir.name:
        candidates.append(session_dir.joinpath(*parts[1:]))

    # local://thermal/file.npz
    candidates.append(session_dir / rel)

    # relative to parent of session directory
    candidates.append(session_dir.parent / rel)

    for c in candidates:
        if c.exists():
            return c
    return candidates[0] if candidates else None


def _thermal_features(window: dict[str, Any], session_dir: str | Path | None) -> dict[str, float]:
    thermal = window.get("thermal") or {}
    health = thermal.get("health")
    out = {
        "thermal_available": _health_available(health),
        "thermal_frame_count_window": _num(thermal.get("frame_count")),
        "thermal_frame_count_npz": 0.0,
        "thermal_mean": 0.0,
        "thermal_std": 0.0,
        "thermal_min": 0.0,
        "thermal_max": 0.0,
        "thermal_p90": 0.0,
        "thermal_p95": 0.0,
        "thermal_p99": 0.0,
        "thermal_hot_threshold": 0.0,
        "thermal_hot_area_ratio": 0.0,
        "thermal_hot_region_count": 0.0,
        "thermal_temporal_std_mean": 0.0,
        "thermal_frame_diff_mean": 0.0,
        "thermal_heat_delta_p95_median": 0.0,
    }

    if health != "ok":
        return out

    p = resolve_frames_ref(session_dir, thermal.get("frames_ref"))
    if p is None or not p.exists():
        return out

    try:
        with np.load(p) as data:
            frames = data["frames"].astype(float)
    except Exception:
        return out

    if frames.size == 0:
        return out

    # Current MLX90640 style is 24 x 32 = 768 values per frame.
    if frames.ndim == 2 and frames.shape[1] == 768:
        frames_3d = frames.reshape((-1, 24, 32))
    elif frames.ndim == 3:
        frames_3d = frames
    else:
        flat = frames.reshape((frames.shape[0], -1))
        if flat.shape[1] == 768:
            frames_3d = flat.reshape((-1, 24, 32))
        else:
            # Unknown shape: still compute global statistics, but no hotspot geometry.
            out.update({
                "thermal_frame_count_npz": float(flat.shape[0]),
                "thermal_mean": float(np.nanmean(flat)),
                "thermal_std": float(np.nanstd(flat)),
                "thermal_min": float(np.nanmin(flat)),
                "thermal_max": float(np.nanmax(flat)),
                "thermal_p90": float(np.nanpercentile(flat, 90)),
                "thermal_p95": float(np.nanpercentile(flat, 95)),
                "thermal_p99": float(np.nanpercentile(flat, 99)),
            })
            return out

    avg = np.nanmean(frames_3d, axis=0)
    threshold = max(float(np.nanpercentile(avg, 90)), float(np.nanmean(avg) + np.nanstd(avg)))
    hot_mask = avg >= threshold
    labeled, hot_regions = ndimage.label(hot_mask, structure=np.ones((3, 3)))

    if frames_3d.shape[0] > 1:
        frame_diff = np.abs(np.diff(frames_3d, axis=0))
        frame_diff_mean = float(np.nanmean(frame_diff))
    else:
        frame_diff_mean = 0.0

    out.update({
        "thermal_frame_count_npz": float(frames_3d.shape[0]),
        "thermal_mean": float(np.nanmean(frames_3d)),
        "thermal_std": float(np.nanstd(frames_3d)),
        "thermal_min": float(np.nanmin(frames_3d)),
        "thermal_max": float(np.nanmax(frames_3d)),
        "thermal_p90": float(np.nanpercentile(frames_3d, 90)),
        "thermal_p95": float(np.nanpercentile(frames_3d, 95)),
        "thermal_p99": float(np.nanpercentile(frames_3d, 99)),
        "thermal_hot_threshold": threshold,
        "thermal_hot_area_ratio": float(np.nanmean(hot_mask)),
        "thermal_hot_region_count": float(hot_regions),
        "thermal_temporal_std_mean": float(np.nanmean(np.nanstd(frames_3d, axis=0))),
        "thermal_frame_diff_mean": frame_diff_mean,
        "thermal_heat_delta_p95_median": float(np.nanpercentile(frames_3d, 95) - np.nanmedian(frames_3d)),
    })
    return out


def _radar_features(window: dict[str, Any]) -> dict[str, float]:
    radar = window.get("radar") or {}
    health = radar.get("health")
    tracks = radar.get("tracks") or []

    valid_targets = 0
    total_targets = 0
    speeds: list[float] = []
    for track in tracks:
        for target in track.get("targets", []) or []:
            total_targets += 1
            if target.get("valid", True):
                valid_targets += 1
                if target.get("speed_cm_s") is not None:
                    speeds.append(abs(_num(target.get("speed_cm_s"))))

    return {
        "radar_available": _health_available(health),
        "radar_sample_count": _num(radar.get("sample_count")),
        "radar_track_count": float(len(tracks)),
        "radar_valid_target_count": float(valid_targets),
        "radar_target_count_total": float(total_targets),
        "radar_mean_speed_cm_s": float(np.mean(speeds)) if speeds else 0.0,
        "radar_max_speed_cm_s": float(np.max(speeds)) if speeds else 0.0,
    }


def _sound_light_features(window: dict[str, Any], relative: dict[str, Any] | None) -> dict[str, float]:
    sound = window.get("sound") or {}
    sound_rel = ((relative or {}).get("sound") or {})
    rms_rel = sound_rel.get("rms") or {}

    rms_mean = _num(sound.get("rms_mean", rms_rel.get("mean")))
    rms_std = _num(sound.get("rms_std", rms_rel.get("std")))
    peak = _num(sound.get("peak", sound_rel.get("peak")))

    light_rel = ((relative or {}).get("light") or {})
    light_norm = light_rel.get("normalized") or {}
    light_adc = light_rel.get("adc") or {}

    return {
        "sound_available": _health_available(sound.get("health")),
        "sound_rms_mean": rms_mean,
        "sound_rms_std": rms_std,
        "sound_peak": peak,
        "sound_rms_min": _num(rms_rel.get("minimum"), rms_mean),
        "sound_rms_max": _num(rms_rel.get("maximum"), rms_mean),
        "sound_sample_count": _num(rms_rel.get("sample_count")),
        "sound_log_rms_mean": float(np.log1p(max(rms_mean, 0.0))),
        "sound_peak_to_rms": float(peak / (rms_mean + 1e-6)),
        "light_proxy_available": 1.0 if light_norm or light_adc else 0.0,
        "light_normalized_mean": _num(light_norm.get("mean")),
        "light_normalized_std": _num(light_norm.get("std")),
        "light_adc_mean": _num(light_adc.get("mean")),
        "light_adc_std": _num(light_adc.get("std")),
        "light_sample_count": _num(light_norm.get("sample_count", light_adc.get("sample_count"))),
    }


def _environment_quality_features(window: dict[str, Any]) -> dict[str, float]:
    env = window.get("environment") or {}
    quality = window.get("quality") or {}
    warnings = quality.get("warnings") or []

    thermal_health = (window.get("thermal") or {}).get("health")
    radar_health = (window.get("radar") or {}).get("health")
    sound_health = (window.get("sound") or {}).get("health")

    start = _parse_time(window.get("window_start"))
    end = _parse_time(window.get("window_end"))
    seconds = (end - start).total_seconds() if start and end else 0.0

    return {
        "env_temperature_c": _num(env.get("temperature_c")),
        "env_humidity_pct": _num(env.get("humidity_pct")),
        "env_temp_missing": 1.0 if env.get("temperature_c") is None else 0.0,
        "env_humidity_missing": 1.0 if env.get("humidity_pct") is None else 0.0,
        "env_light_lux_missing": 1.0 if env.get("light_lux") is None else 0.0,
        "quality_completeness": _num(quality.get("completeness"), 0.0),
        "quality_warning_count": float(len(warnings)),
        "sensor_unavailable_count": float(sum(_is_unavailable(h) for h in [thermal_health, radar_health, sound_health])),
        "sensor_degraded_count": float(sum(_is_degraded(h) for h in [thermal_health, radar_health, sound_health])),
        "window_seconds_actual": float(seconds),
    }


def extract_window_features(
    window: dict[str, Any],
    *,
    session_dir: str | Path | None = None,
    relative: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract a model-ready feature row from one SensorWindow.

    The returned dict includes identifiers plus all numeric people-count features.
    """
    row: dict[str, Any] = {
        "session_id": Path(session_dir).name if session_dir else window.get("session_id", ""),
        "window_id": window.get("window_id", ""),
        "room_id": window.get("room_id", ""),
        "device_id": window.get("device_id", ""),
        "window_start": window.get("window_start", ""),
        "window_end": window.get("window_end", ""),
    }

    row.update(_thermal_features(window, session_dir))
    row.update(_radar_features(window))
    row.update(_sound_light_features(window, relative))
    row.update(_environment_quality_features(window))

    for name in PEOPLE_COUNT_FEATURE_NAMES:
        row.setdefault(name, 0.0)

    return row


def as_feature_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    for name in PEOPLE_COUNT_FEATURE_NAMES:
        if name not in df.columns:
            df[name] = 0.0
        df[name] = pd.to_numeric(df[name], errors="coerce")
    return df
