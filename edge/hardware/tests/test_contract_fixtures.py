from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


REPOSITORY_ROOT = Path(__file__).parents[3]


def test_all_sensor_window_fixtures_match_schema() -> None:
    schema = json.loads(
        (REPOSITORY_ROOT / "shared/contracts/sensor_window.schema.json").read_text()
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    fixture_paths = sorted(
        (REPOSITORY_ROOT / "shared/fixtures").glob("sensor_window_*.json")
    )
    assert len(fixture_paths) >= 5
    for path in fixture_paths:
        payload = json.loads(path.read_text())
        errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
        assert not errors, f"{path.name}: {[error.message for error in errors]}"
