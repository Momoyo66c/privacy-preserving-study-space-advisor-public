from __future__ import annotations

import json
from pathlib import Path

from study_space_ml.contracts import validate_payload
from study_space_ml.predictor import EdgePredictor


ROOT = Path(__file__).resolve().parents[3]


def load_fixture(name: str) -> dict:
    with (ROOT / "shared" / "fixtures" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_quiet_fixture_predicts_valid_observation() -> None:
    predictor = EdgePredictor()
    observation = predictor.predict_window(load_fixture("sensor_window_quiet.json"))
    assert observation["room_state"] == "quiet_study_recommended"
    assert observation["occupancy_level"] == "low"
    validate_payload(observation, "edge_observation.schema.json", repo_root=ROOT)


def test_empty_fixture_predicts_empty_or_low_activity() -> None:
    predictor = EdgePredictor()
    observation = predictor.predict_window(load_fixture("sensor_window_empty.json"))
    assert observation["room_state"] == "empty_or_low_activity"
    assert observation["occupancy_level"] == "empty"
    validate_payload(observation, "edge_observation.schema.json", repo_root=ROOT)


def test_degraded_fixture_keeps_contract_and_warning() -> None:
    predictor = EdgePredictor()
    observation = predictor.predict_window(load_fixture("sensor_window_degraded.json"))
    assert observation["sensor_health"]["thermal"] == "offline"
    assert observation["sensor_health"]["environment"] == "degraded"
    assert any("thermal" in warning for warning in observation["warnings"])
    validate_payload(observation, "edge_observation.schema.json", repo_root=ROOT)
