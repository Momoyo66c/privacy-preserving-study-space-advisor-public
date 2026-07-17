from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

import pytest

from study_space_hardware.cli import collect_main, probe_main, simulator_main


EXAMPLE_CONFIG = Path(__file__).parents[1] / "config/example.yaml"


@pytest.mark.parametrize("entrypoint", [simulator_main, probe_main, collect_main])
def test_sensor_cli_requires_explicit_config(
    entrypoint: Callable[[Sequence[str] | None], int],
) -> None:
    with pytest.raises(SystemExit) as raised:
        entrypoint([])
    assert raised.value.code == 2


def test_simulator_cli_outputs_contract_window(capsys) -> None:
    result = simulator_main(
        ["--config", str(EXAMPLE_CONFIG), "--windows", "1"]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1.0"
    assert payload["thermal"]["frame_count"] == 10


def test_probe_cli_outputs_only_safe_sensor_summaries(capsys) -> None:
    result = probe_main(["--config", str(EXAMPLE_CONFIG)])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"thermal", "radar", "sound", "light", "climate"}
    assert payload["thermal"]["sample"]["frame_shape"] == [24, 32]
    assert "temperatures_c" not in json.dumps(payload["thermal"])
    assert payload["sound"]["sample"]["raw_audio_persisted"] is False


def test_collection_cli_does_not_eagerly_import_validation_stack() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import study_space_hardware.cli; "
                "assert 'numpy' not in sys.modules; "
                "assert 'jsonschema' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
