from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from study_space_ml.constants import DEFAULT_ORDERED_FEATURES
from study_space_ml.features.environment import extract_environment_features
from study_space_ml.features.radar import extract_radar_features
from study_space_ml.features.sound import extract_sound_features
from study_space_ml.features.thermal import extract_thermal_features


@dataclass(frozen=True, slots=True)
class FeatureBundle:
    features: dict[str, Any]
    summary: dict[str, Any]
    warnings: list[str]


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def extract_feature_bundle(window: dict[str, Any], *, session_dir: str | Path | None = None) -> FeatureBundle:
    thermal_features, thermal_warnings = extract_thermal_features(window, session_dir=session_dir)
    radar_features = extract_radar_features(window)
    sound_features = extract_sound_features(window)
    environment_features = extract_environment_features(window)
    quality = window.get("quality") or {}
    features: dict[str, Any] = {}
    features.update(thermal_features)
    features.update(radar_features)
    features.update(sound_features)
    features.update(environment_features)
    features["quality_completeness"] = quality.get("completeness")
    summary = {
        "thermal_hot_region_count": thermal_features["thermal_hot_region_count"],
        "radar_active_target_count": radar_features["radar_max_target_count"],
        "sound_rms_mean": sound_features["sound_rms_mean"],
        "light_lux": environment_features["light_lux"],
        "temperature_c": environment_features["temperature_c"],
        "humidity_pct": environment_features["humidity_pct"],
    }
    warnings = [*thermal_warnings]
    for item in quality.get("warnings") or []:
        warnings.append(f"INPUT_WARNING:{item}")
    return FeatureBundle(features=features, summary=summary, warnings=warnings)


def feature_vector(features: dict[str, Any], ordered_features: list[str] | None = None) -> list[float]:
    names = ordered_features or DEFAULT_ORDERED_FEATURES
    return [_as_float(features.get(name), 0.0) for name in names]
