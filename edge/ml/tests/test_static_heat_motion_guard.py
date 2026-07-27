import json

import numpy as np
import pandas as pd

from study_space_ml.features import extract_window_features
from study_space_ml.predictor import PeopleCountPredictor
from study_space_ml.train import train_people_count_model


def _window(session_id, window_id, sound=0.001):
    return {
        "window_id": window_id,
        "room_id": "room_a",
        "device_id": "pi5-a",
        "window_start": "2026-07-23T10:00:00Z",
        "window_end": "2026-07-23T10:00:05Z",
        "thermal": {"health": "ok", "frame_count": 4, "frames_ref": f"local://{session_id}/thermal/{window_id}.npz"},
        "radar": {"health": "ok", "sample_count": 4, "tracks": []},
        "sound": {"health": "ok", "rms_mean": sound, "rms_std": 0.0001, "peak": sound * 1.5},
        "environment": {"light_lux": None, "temperature_c": 25.0, "humidity_pct": 50.0},
        "quality": {"completeness": 1.0, "warnings": []},
    }


def _static_laptop_frames():
    frames = np.ones((4, 24, 32), dtype="float32") * 25.0
    frames[:, 18:21, 20:23] = 36.0
    return frames.reshape((4, 768))


def _moving_person_frames():
    frames = np.ones((4, 24, 32), dtype="float32") * 25.0
    for i in range(4):
        frames[i, 12 + i:15 + i, 10 + i:13 + i] = 36.0
    return frames.reshape((4, 768))


def test_static_source_has_high_static_score(tmp_path):
    session = tmp_path / "session-static"
    (session / "thermal").mkdir(parents=True)
    np.savez(session / "thermal" / "w0.npz", frames=_static_laptop_frames())

    feats = extract_window_features(_window("session-static", "w0"), session_dir=session)
    assert feats["thermal_static_heat_score"] > 0.80
    assert feats["thermal_main_hot_centroid_path_px"] < 0.50
    assert feats["thermal_hot_motion_ratio"] == 0.0


def test_moving_source_has_motion_path(tmp_path):
    session = tmp_path / "session-moving"
    (session / "thermal").mkdir(parents=True)
    np.savez(session / "thermal" / "w0.npz", frames=_moving_person_frames())

    feats = extract_window_features(_window("session-moving", "w0"), session_dir=session)
    assert feats["thermal_main_hot_centroid_path_px"] > 1.0
    assert feats["thermal_hot_motion_ratio"] > 0.0


def test_sequence_guard_marks_static_computer_candidate(tmp_path):
    labels = []
    for sid, count, frames_fn in [
        ("session-empty", 0, _static_laptop_frames),
        ("session-person", 1, _moving_person_frames),
    ]:
        session = tmp_path / sid
        (session / "thermal").mkdir(parents=True)
        rows = []
        for i in range(4):
            wid = f"w{i}"
            np.savez(session / "thermal" / f"{wid}.npz", frames=frames_fn())
            rows.append(json.dumps(_window(sid, wid)))
            labels.append({"session_id": sid, "window_id": wid, "people_count": count})
        (session / "windows.jsonl").write_text("\n".join(rows), encoding="utf-8")
        (session / "session.json").write_text(json.dumps({"session_id": sid, "participant_range": str(count)}), encoding="utf-8")

    pd.DataFrame(labels).to_csv(tmp_path / "labels.csv", index=False)
    artifact = tmp_path / "artifact"
    train_people_count_model(tmp_path, labels_path=tmp_path / "labels.csv", out_dir=artifact)

    records = PeopleCountPredictor(artifact).predict_path(tmp_path / "session-empty", out_path=tmp_path / "predictions.jsonl", include_features=True)
    assert any("STATIC_HEAT_SOURCE" in " ".join(r.get("warnings", [])) for r in records)
