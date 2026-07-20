from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


HARDWARE_ROOT = Path(__file__).parents[1]
FIRMWARE_ROOT = HARDWARE_ROOT / "firmware/esp32_sensor_hub"
HARNESS = HARDWARE_ROOT / "tests/cpp/esp32_protocol_golden.cpp"


def test_firmware_protocol_matches_python_golden_vector(tmp_path: Path) -> None:
    compiler = shutil.which("c++")
    if compiler is None:
        pytest.skip("a C++ compiler is required for the firmware golden test")
    binary = tmp_path / "esp32-protocol-golden"
    subprocess.run(
        [
            compiler,
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(FIRMWARE_ROOT / "protocol.cpp"),
            str(HARNESS),
            f"-I{FIRMWARE_ROOT}",
            "-o",
            str(binary),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run([str(binary)], check=True, capture_output=True, text=True)


def test_firmware_never_emits_text_or_raw_audio_protocol_types() -> None:
    source = (FIRMWARE_ROOT / "esp32_sensor_hub.ino").read_text()
    protocol = (FIRMWARE_ROOT / "protocol.h").read_text()

    assert "Serial.print" not in source
    assert "Serial.println" not in source
    assert "recordWAV" not in source
    assert "PCM" not in protocol
    assert "kRawAudio" not in protocol


def test_firmware_retries_sensors_missing_at_boot() -> None:
    source = (FIRMWARE_ROOT / "esp32_sensor_hub.ino").read_text()
    config = (FIRMWARE_ROOT / "sensor_hub_config.h").read_text()

    assert "retryFailedInitializations(now);" in source
    assert "!thermal_initialized" in source
    assert "!light_initialized" in source
    assert "!climate_initialized" in source
    assert "!sound_initialized" in source
    assert "kInitializationRetryIntervalMs = 5000" in config
