import json
from pathlib import Path

import numpy as np

from study_space_ml.features import extract_window_features


def test_extract_window_features_with_npz(tmp_path):
    session = tmp_path / "session-test"
    (session / "thermal").mkdir(parents=True)
    frames = np.ones((2, 768), dtype="float32") * 25
    frames[:, 100:110] = 35
    np.savez(session / "thermal" / "w1.npz", frames=frames)

    window = {
        "window_id": "w1",
        "room_id": "room_a",
        "device_id": "pi5-a",
        "window_start": "2026-07-23T10:00:00Z",
        "window_end": "2026-07-23T10:00:05Z",
        "thermal": {"health": "ok", "frame_count": 2, "frames_ref": "local://session-test/thermal/w1.npz"},
        "radar": {"health": "not_configured", "sample_count": 0, "tracks": []},
        "sound": {"health": "ok", "rms_mean": 0.1, "rms_std": 0.01, "peak": 0.2},
        "environment": {"light_lux": None, "temperature_c": 25.0, "humidity_pct": 50.0},
        "quality": {"completeness": 0.8, "warnings": []},
    }

    feats = extract_window_features(window, session_dir=session)
    assert feats["thermal_frame_count_npz"] == 2
    assert feats["thermal_max"] > feats["thermal_mean"]
    assert feats["sound_rms_mean"] == 0.1
    assert feats["window_seconds_actual"] == 5.0


def test_extract_window_features_accepts_in_memory_thermal_frames():
    frames = np.ones((2, 768), dtype="float32") * 25
    frames[:, 100:110] = 35
    window = {
        "window_id": "w-live",
        "room_id": "room_a",
        "device_id": "pi5-a",
        "window_start": "2026-07-23T10:00:00Z",
        "window_end": "2026-07-23T10:00:05Z",
        "thermal": {"health": "ok", "frame_count": 2, "frames_ref": None},
        "radar": {"health": "not_configured", "sample_count": 0, "tracks": []},
        "sound": {"health": "ok", "rms_mean": 0.1, "rms_std": 0.01, "peak": 0.2},
        "environment": {"light_lux": None, "temperature_c": 25.0, "humidity_pct": 50.0},
        "quality": {"completeness": 0.8, "warnings": []},
    }

    feats = extract_window_features(window, thermal_frames=frames)

    assert feats["thermal_available"] == 1.0
    assert feats["thermal_frame_count_npz"] == 2
    assert feats["thermal_max"] > feats["thermal_mean"]
