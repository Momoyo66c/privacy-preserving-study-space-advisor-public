import json
import numpy as np
import pandas as pd

from study_space_ml.predictor import PeopleCountPredictor
from study_space_ml.train import train_people_count_model


def test_predictor_smoke(tmp_path):
    session = tmp_path / "session-a"
    (session / "thermal").mkdir(parents=True)
    labels = []
    windows = []
    for i, count in enumerate([0, 1, 2, 2]):
        wid = f"w{i}"
        frames = np.ones((2, 768), dtype="float32") * (25 + count)
        np.savez(session / "thermal" / f"{wid}.npz", frames=frames)
        w = {
            "window_id": wid,
            "room_id": "room_a",
            "device_id": "pi5-a",
            "window_start": "2026-07-23T10:00:00Z",
            "window_end": "2026-07-23T10:00:05Z",
            "thermal": {"health": "ok", "frame_count": 2, "frames_ref": f"local://session-a/thermal/{wid}.npz"},
            "radar": {"health": "not_configured", "sample_count": 0, "tracks": []},
            "sound": {"health": "ok", "rms_mean": count * 0.1, "rms_std": 0.01, "peak": count * 0.2},
            "environment": {"light_lux": None, "temperature_c": 25.0, "humidity_pct": 50.0},
            "quality": {"completeness": 0.8, "warnings": []},
        }
        windows.append(w)
        labels.append({"session_id": "session-a", "window_id": wid, "people_count": count})
    (session / "windows.jsonl").write_text("\n".join(json.dumps(w) for w in windows), encoding="utf-8")
    (session / "session.json").write_text(json.dumps({"session_id": "session-a", "participant_range": "0-2"}), encoding="utf-8")
    pd.DataFrame(labels).to_csv(tmp_path / "labels.csv", index=False)

    artifact = tmp_path / "artifact"
    train_people_count_model(tmp_path, labels_path=tmp_path / "labels.csv", out_dir=artifact)
    pred = PeopleCountPredictor(artifact).predict_window(windows[-1], session_dir=session)
    assert "predicted_people_count" in pred
    assert pred["predicted_people_count_rounded"] >= 0
