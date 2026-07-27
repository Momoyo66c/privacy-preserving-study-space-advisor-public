import json
from pathlib import Path

import numpy as np
import pandas as pd

from study_space_ml.train import train_people_count_model


def _make_session(root, sid, count, sound):
    session = root / sid
    (session / "thermal").mkdir(parents=True)
    rows = []
    label_rows = []
    for i in range(3):
        wid = f"room_a-test-{sid}-{i}"
        frames = np.ones((2, 768), dtype="float32") * (25 + count)
        frames[:, 100:110] += 5 + count
        np.savez(session / "thermal" / f"{wid}.npz", frames=frames)
        window = {
            "window_id": wid,
            "room_id": "room_a",
            "device_id": "pi5-a",
            "window_start": "2026-07-23T10:00:00Z",
            "window_end": "2026-07-23T10:00:05Z",
            "thermal": {"health": "ok", "frame_count": 2, "frames_ref": f"local://{sid}/thermal/{wid}.npz"},
            "radar": {"health": "not_configured", "sample_count": 0, "tracks": []},
            "sound": {"health": "ok", "rms_mean": sound, "rms_std": 0.01, "peak": sound * 2},
            "environment": {"light_lux": None, "temperature_c": 25.0, "humidity_pct": 50.0},
            "quality": {"completeness": 0.8, "warnings": []},
        }
        rows.append(json.dumps(window))
        label_rows.append({"session_id": sid, "window_id": wid, "people_count": count})
    (session / "windows.jsonl").write_text("\n".join(rows), encoding="utf-8")
    (session / "session.json").write_text(json.dumps({
        "session_id": sid,
        "scenario": "test",
        "participant_range": str(count),
        "window_count": 3,
    }), encoding="utf-8")
    return label_rows


def test_train_model(tmp_path):
    labels = []
    labels += _make_session(tmp_path, "session-a", 0, 0.001)
    labels += _make_session(tmp_path, "session-b", 2, 0.2)
    pd.DataFrame(labels).to_csv(tmp_path / "labels.csv", index=False)

    out = tmp_path / "artifact"
    meta = train_people_count_model(tmp_path, labels_path=tmp_path / "labels.csv", out_dir=out)
    assert (out / "model.joblib").exists()
    assert meta["training_rows"] == 6
