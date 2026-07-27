from __future__ import annotations

from typing import Any


def extract_sound_features(window: dict[str, Any]) -> dict[str, Any]:
    sound = window.get("sound") or {}
    health = sound.get("health")
    rms_mean = sound.get("rms_mean")
    rms_std = sound.get("rms_std")
    peak = sound.get("peak")
    missing = 1 if health in {"offline", "not_configured"} or rms_mean is None else 0
    return {
        "sound_rms_mean": rms_mean,
        "sound_rms_std": rms_std,
        "sound_peak": peak,
        "sound_missing": missing,
    }
