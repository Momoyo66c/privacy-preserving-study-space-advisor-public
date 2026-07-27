from __future__ import annotations

import math
from typing import Any


def extract_radar_features(window: dict[str, Any]) -> dict[str, Any]:
    radar = window.get("radar") or {}
    tracks = radar.get("tracks") or []
    counts: list[int] = []
    speeds: list[float] = []
    distances: list[float] = []
    for track in tracks:
        if not isinstance(track, dict):
            continue
        targets = track.get("targets") or []
        if not isinstance(targets, list):
            continue
        valid_targets = [target for target in targets if isinstance(target, dict) and target.get("valid", True) is True]
        counts.append(len(valid_targets))
        for target in valid_targets:
            speed = target.get("speed_cm_s")
            x = target.get("x_mm")
            y = target.get("y_mm")
            if isinstance(speed, (int, float)) and not isinstance(speed, bool):
                speeds.append(abs(float(speed)))
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                distances.append(math.sqrt(float(x) ** 2 + float(y) ** 2))
    sample_count = int(radar.get("sample_count") or 0)
    latest = counts[-1] if counts else 0
    max_count = max(counts) if counts else 0
    active_frames = sum(1 for count in counts if count > 0)
    denominator = len(counts) if counts else max(sample_count, 1)
    return {
        "radar_latest_target_count": latest,
        "radar_max_target_count": max_count,
        "radar_active_frame_ratio": active_frames / denominator if denominator else 0.0,
        "radar_mean_abs_speed_cm_s": sum(speeds) / len(speeds) if speeds else None,
        "radar_mean_distance_mm": sum(distances) / len(distances) if distances else None,
    }
