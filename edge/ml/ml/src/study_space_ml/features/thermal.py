from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

from study_space_ml.paths import resolve_local_ref


def _connected_components(mask: list[list[bool]]) -> int:
    if not mask:
        return 0
    height = len(mask)
    width = len(mask[0]) if height else 0
    seen = [[False] * width for _ in range(height)]
    count = 0
    for y in range(height):
        for x in range(width):
            if not mask[y][x] or seen[y][x]:
                continue
            count += 1
            queue = deque([(y, x)])
            seen[y][x] = True
            while queue:
                cy, cx = queue.popleft()
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dy == 0 and dx == 0:
                            continue
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < height and 0 <= nx < width and mask[ny][nx] and not seen[ny][nx]:
                            seen[ny][nx] = True
                            queue.append((ny, nx))
    return count


def _thermal_npz_summary(path: Path) -> dict[str, Any] | None:
    try:
        import numpy as np  # type: ignore
        from study_space_ml.features.people_count import thermal_motion_summary_from_frames
    except Exception:
        return None

    try:
        data = np.load(path)
        frames = data["frames"]
        arr = np.asarray(frames, dtype=float)
        if arr.ndim == 2 and arr.shape[1] == 768:
            arr = arr.reshape((arr.shape[0], 24, 32))
        elif arr.ndim == 3 and arr.shape[1:] == (24, 32):
            pass
        else:
            return None
        if arr.size == 0:
            return None

        avg = np.nanmean(arr, axis=0)
        finite = avg[np.isfinite(avg)]
        if finite.size == 0:
            return None
        threshold = max(float(np.percentile(finite, 90)), float(np.mean(finite) + np.std(finite)))
        mask = [[bool(value >= threshold) for value in row] for row in avg.tolist()]
        summary = {
            "thermal_hot_region_count": _connected_components(mask),
            "thermal_frame_diff_mean": float(np.nanmean(np.abs(np.diff(arr, axis=0)))) if arr.shape[0] > 1 else 0.0,
        }
        summary.update(thermal_motion_summary_from_frames(arr))
        return summary
    except Exception:
        return None


def _thermal_hot_regions_from_npz(path: Path) -> int | None:
    summary = _thermal_npz_summary(path)
    if summary is None:
        return None
    return int(summary["thermal_hot_region_count"])


def extract_thermal_features(window: dict[str, Any], *, session_dir: str | Path | None = None) -> tuple[dict[str, Any], list[str]]:
    thermal = window.get("thermal") or {}
    warnings: list[str] = []
    health = thermal.get("health")
    frame_count = int(thermal.get("frame_count") or 0)
    missing = 1 if health in {"offline", "not_configured"} or frame_count == 0 else 0
    frames_path = resolve_local_ref(thermal.get("frames_ref"), session_dir=session_dir)

    summary: dict[str, Any] | None = None
    if frames_path is not None:
        summary = _thermal_npz_summary(frames_path)
        if summary is None:
            warnings.append("THERMAL_NPZ_UNREADABLE_OR_NUMPY_MISSING")
    elif thermal.get("frames_ref"):
        warnings.append("THERMAL_FRAMES_REF_NOT_FOUND")
    else:
        warnings.append("THERMAL_FRAMES_NOT_AVAILABLE")

    hot_region_count = None if summary is None else summary.get("thermal_hot_region_count")
    if missing:
        hot_region_count = None

    return {
        "thermal_frame_count": frame_count,
        "thermal_hot_region_count": hot_region_count,
        "thermal_missing": missing,
        "thermal_frame_diff_mean": None if summary is None else summary.get("thermal_frame_diff_mean"),
        "thermal_static_heat_score": None if summary is None else summary.get("thermal_static_heat_score"),
        "thermal_main_hot_centroid_path_px": None if summary is None else summary.get("thermal_main_hot_centroid_path_px"),
        "thermal_hot_motion_ratio": None if summary is None else summary.get("thermal_hot_motion_ratio"),
    }, warnings
