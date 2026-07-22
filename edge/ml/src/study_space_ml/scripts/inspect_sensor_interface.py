from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from study_space_ml.data.io import load_windows
from study_space_ml.data.validation import validate_window_collection
from study_space_ml.paths import infer_session_dir, resolve_windows_path


def _health_counts(windows: list[dict[str, Any]], sensor: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for window in windows:
        if sensor == "environment":
            env = window.get("environment") or {}
            values = [env.get("light_lux"), env.get("temperature_c"), env.get("humidity_pct")]
            status = "offline" if all(value is None for value in values) else "degraded" if any(value is None for value in values) else "ok"
        else:
            status = str((window.get(sensor) or {}).get("health") or "not_configured")
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _first_shape(window: dict[str, Any]) -> dict[str, Any]:
    radar_tracks = (window.get("radar") or {}).get("tracks") or []
    first_track = radar_tracks[0] if radar_tracks else {}
    targets = first_track.get("targets") if isinstance(first_track, dict) else []
    first_target = targets[0] if isinstance(targets, list) and targets else None
    return {
        "top_level_keys": sorted(window.keys()),
        "thermal_keys": sorted((window.get("thermal") or {}).keys()),
        "radar_keys": sorted((window.get("radar") or {}).keys()),
        "radar_track_keys": sorted(first_track.keys()) if isinstance(first_track, dict) else [],
        "radar_target_keys": sorted(first_target.keys()) if isinstance(first_target, dict) else [],
        "sound_keys": sorted((window.get("sound") or {}).keys()),
        "environment_keys": sorted((window.get("environment") or {}).keys()),
        "quality_keys": sorted((window.get("quality") or {}).keys()),
    }


def inspect_interface(path: str | Path) -> dict[str, Any]:
    windows_path = resolve_windows_path(path) if Path(path).expanduser().exists() and (Path(path).expanduser().is_dir() or str(path).endswith(".jsonl")) else Path(path)
    session_dir = infer_session_dir(path)
    windows = load_windows(path)
    report = validate_window_collection(windows)
    result: dict[str, Any] = {
        "input": str(path),
        "windows_path": str(windows_path),
        "session_dir": str(session_dir) if session_dir else None,
        "window_count": len(windows),
        "contract_valid": report["valid"],
        "errors": report["errors"],
        "warnings": report["warnings"][:20],
    }
    if not windows:
        result["shape"] = None
        return result
    result["first_window_id"] = windows[0].get("window_id")
    result["first_shape"] = _first_shape(windows[0])
    result["sensor_health_counts"] = {
        "thermal": _health_counts(windows, "thermal"),
        "radar": _health_counts(windows, "radar"),
        "sound": _health_counts(windows, "sound"),
        "environment": _health_counts(windows, "environment"),
    }
    result["window_id_policy"] = "Use window_id for labels and observation id seed. Do not treat radar target_id as identity across windows."
    result["thermal_frames_policy"] = "thermal.frames_ref is local-only. Use it for offline feature extraction when the NPZ exists; never send raw frames to backend."
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect the Module 1 SensorWindow interface seen by Module 2.")
    parser.add_argument("input", help="sensor_window.json, windows.jsonl, or session directory")
    parser.add_argument("--out", help="optional JSON report path")
    args = parser.parse_args(argv)
    report = inspect_interface(args.input)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("contract_valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
