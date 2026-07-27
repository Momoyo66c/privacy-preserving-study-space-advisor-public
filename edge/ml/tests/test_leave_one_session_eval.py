import json

import numpy as np
import pandas as pd

from study_space_ml.evaluation import evaluate_leave_one_session


def _make_session(root, sid, count, sound):
    session = root / sid
    (session / "thermal").mkdir(parents=True)
    labels = []
    rows = []

    for i in range(3):
        wid = f"{sid}-w{i}"
        frames = np.ones((4, 768), dtype="float32") * (25 + count)
        frames[:, 100:108] += 4 + count
        np.savez(session / "thermal" / f"{wid}.npz", frames=frames)

        window = {
            "window_id": wid,
            "room_id": "room_a",
            "device_id": "pi5-a",
            "window_start": "2026-07-23T10:00:00Z",
            "window_end": "2026-07-23T10:00:05Z",
            "thermal": {"health": "ok", "frame_count": 4, "frames_ref": f"local://{sid}/thermal/{wid}.npz"},
            "radar": {"health": "not_configured", "sample_count": 0, "tracks": []},
            "sound": {"health": "ok", "rms_mean": sound, "rms_std": 0.01, "peak": sound * 2},
            "environment": {"light_lux": None, "temperature_c": 25.0, "humidity_pct": 50.0},
            "quality": {"completeness": 1.0, "warnings": []},
        }
        rows.append(json.dumps(window))
        labels.append({"session_id": sid, "window_id": wid, "people_count": count, "label": f"count_{count}"})

    (session / "windows.jsonl").write_text("\n".join(rows), encoding="utf-8")
    (session / "session.json").write_text(json.dumps({"session_id": sid, "participant_range": str(count)}), encoding="utf-8")
    return labels


def test_leave_one_session_eval_outputs_files(tmp_path):
    labels = []
    labels += _make_session(tmp_path, "session-zero", 0, 0.001)
    labels += _make_session(tmp_path, "session-one", 1, 0.08)
    labels += _make_session(tmp_path, "session-two", 2, 0.20)
    pd.DataFrame(labels).to_csv(tmp_path / "labels.csv", index=False)

    out_dir = tmp_path / "leave_one_session"
    summary = evaluate_leave_one_session(tmp_path, labels_path=tmp_path / "labels.csv", out_dir=out_dir)

    assert summary["session_count"] == 3
    assert summary["window_count"] == 9
    assert "rounded_accuracy" in summary["overall_metrics"]
    assert (out_dir / "leave_one_session_predictions.csv").exists()
    assert (out_dir / "leave_one_session_metrics_by_session.csv").exists()
    assert (out_dir / "leave_one_session_metrics_overall.json").exists()
    assert (out_dir / "leave_one_session_report.html").exists()
