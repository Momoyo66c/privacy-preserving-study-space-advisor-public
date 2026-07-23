from __future__ import annotations

import json
from pathlib import Path

from study_space_ml.inference.predictor import EdgePredictor


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_fixture(name: str) -> dict:
    return json.loads((repo_root() / "shared" / "fixtures" / name).read_text(encoding="utf-8"))


def test_predict_quiet_fixture() -> None:
    payload = EdgePredictor().predict_window(load_fixture("sensor_window_quiet.json"))
    assert payload["room_state"] == "quiet_study_recommended"
    assert payload["occupancy_level"] == "low"
    assert 0 <= payload["suitability_score"] <= 100
    assert 0 <= payload["confidence"] <= 1
    assert payload["features"]["sound_rms_mean"] == 0.121


def test_predict_crowded_fixture() -> None:
    payload = EdgePredictor().predict_window(load_fixture("sensor_window_crowded.json"))
    assert payload["room_state"] == "not_recommended_noisy_or_crowded"
    assert payload["occupancy_level"] == "high"


def test_degraded_fixture_still_predicts_or_warns() -> None:
    payload = EdgePredictor().predict_window(load_fixture("sensor_window_degraded.json"))
    assert payload["sensor_health"]["thermal"] == "offline"
    assert payload["sensor_health"]["environment"] == "degraded"
    assert payload["warnings"]
