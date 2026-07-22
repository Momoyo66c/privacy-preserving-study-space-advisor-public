from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


HARDWARE_ROOT = Path(__file__).parents[1]
FIRMWARE_ROOT = HARDWARE_ROOT / "firmware/esp32_sensor_hub"
HARNESS = HARDWARE_ROOT / "tests/cpp/esp32_protocol_golden.cpp"
PROFILE_HARNESS = HARDWARE_ROOT / "tests/cpp/thermal_profile_config.cpp"


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


def test_firmware_matches_identified_sensor_models_and_pins() -> None:
    source = (FIRMWARE_ROOT / "esp32_sensor_hub.ino").read_text()
    config = (FIRMWARE_ROOT / "sensor_hub_config.h").read_text()
    profile = (FIRMWARE_ROOT / "sketch.yaml").read_text()

    assert "DHT dht11" in source
    assert "analogRead(pssa_config::kSoundAdcPin)" in source
    assert "analogRead(pssa_config::kLightAdcPin)" in source
    assert "kDht11DataPin = 27" in config
    assert "kSoundAdcPin = 34" in config
    assert "kLightAdcPin = 35" in config
    assert "kI2cSdaPin = 21" in config
    assert "kI2cSclPin = 22" in config
    assert "kClimateIntervalMs = 2000" in config
    assert "kEnableRadar = false" in config
    assert "DHT sensor library (1.4.6)" in profile
    assert "Adafruit AHTX0" not in profile
    assert "ESP_I2S" not in source


def test_quiet_hw485_zero_baseline_is_a_valid_sample() -> None:
    source = (FIRMWARE_ROOT / "esp32_sensor_hub.ino").read_text()
    config = (FIRMWARE_ROOT / "sensor_hub_config.h").read_text()

    assert "maximum - minimum <= 4" not in source
    assert "kSoundRailGuardCounts" not in source
    assert "kSoundRailGuardCounts" not in config
    assert "const double mean_raw" in source
    assert "writeFloatLe(payload, rms)" in source


@pytest.mark.parametrize(
    ("profile", "i2c_hz", "serial_baud", "refresh_hz", "publish_fps"),
    [
        (0, 400_000, 460_800, 8, 2),
        (1, 1_000_000, 460_800, 32, 16),
        (2, 1_000_000, 921_600, 64, 32),
    ],
)
def test_thermal_profiles_compile_with_safe_bandwidth(
    tmp_path: Path,
    profile: int,
    i2c_hz: int,
    serial_baud: int,
    refresh_hz: int,
    publish_fps: int,
) -> None:
    compiler = shutil.which("c++")
    if compiler is None:
        pytest.skip("a C++ compiler is required for thermal profile tests")
    binary = tmp_path / f"thermal-profile-{profile}"
    subprocess.run(
        [
            compiler,
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            f"-DPSSA_THERMAL_PROFILE={profile}",
            f"-DEXPECT_I2C_RUNTIME_HZ={i2c_hz}",
            f"-DEXPECT_SERIAL_BAUD={serial_baud}",
            f"-DEXPECT_REFRESH_HZ={refresh_hz}",
            f"-DEXPECT_PUBLISH_FPS={publish_fps}",
            str(PROFILE_HARNESS),
            f"-I{FIRMWARE_ROOT}",
            "-o",
            str(binary),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run([str(binary)], check=True, capture_output=True, text=True)


def test_unsupported_thermal_profile_fails_at_compile_time(tmp_path: Path) -> None:
    compiler = shutil.which("c++")
    if compiler is None:
        pytest.skip("a C++ compiler is required for thermal profile tests")
    result = subprocess.run(
        [
            compiler,
            "-std=c++17",
            "-DPSSA_THERMAL_PROFILE=99",
            "-DEXPECT_I2C_RUNTIME_HZ=0",
            "-DEXPECT_SERIAL_BAUD=0",
            "-DEXPECT_REFRESH_HZ=0",
            "-DEXPECT_PUBLISH_FPS=1",
            str(PROFILE_HARNESS),
            f"-I{FIRMWARE_ROOT}",
            "-o",
            str(tmp_path / "invalid-profile"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "unsupported PSSA_THERMAL_PROFILE" in result.stderr


def test_thermal_service_uses_profile_rate_without_starving_sound() -> None:
    source = (FIRMWARE_ROOT / "esp32_sensor_hub.ino").read_text()
    config = (FIRMWARE_ROOT / "sensor_hub_config.h").read_text()

    assert "setRefreshRate(MLX90640_8_HZ)" in source
    assert "setRefreshRate(MLX90640_32_HZ)" in source
    assert "setRefreshRate(MLX90640_64_HZ)" in source
    assert "kThermalIntervalUs" in source
    assert "serviceThermal(micros())" in source
    assert "kSerialUtilizationLimitPercent = 80" in config
    assert "kSoundIntervalMs = 250" in config
