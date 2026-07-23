from __future__ import annotations

from pathlib import Path

from study_space_ml.inference.payload import _stable_id
from study_space_ml.scripts.inspect_sensor_interface import inspect_interface


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_inspect_sensor_interface_reports_fixture_shape() -> None:
    report = inspect_interface(repo_root() / "shared" / "fixtures" / "sensor_window_quiet.json")
    assert report["contract_valid"] is True
    assert report["first_shape"]["radar_target_keys"] == [
        "distance_resolution_mm",
        "speed_cm_s",
        "target_id",
        "valid",
        "x_mm",
        "y_mm",
    ]


def test_stable_id_keeps_hash_under_backend_limit() -> None:
    value = _stable_id("room_a-" + "x" * 300, "0.3.0")
    assert len(value) <= 128
    assert value[-11] == "-"
    assert len(value.rsplit("-", 1)[-1]) == 10
