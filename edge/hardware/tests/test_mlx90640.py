from __future__ import annotations

import math

import pytest

from study_space_hardware.clock import ManualClock
from study_space_hardware.drivers.mlx90640 import MLX90640Driver
from study_space_hardware.drivers.base import SensorValidationError
from study_space_hardware.models import THERMAL_PIXELS


class FakeMlx:
    def __init__(self, frame: list[float]) -> None:
        self.frame = frame

    def getFrame(self, output: list[float]) -> None:
        output[:] = self.frame


class SequencedFakeMlx:
    def __init__(self, frames: list[list[float]]) -> None:
        self.frames = list(frames)

    def getFrame(self, output: list[float]) -> None:
        output[:] = self.frames.pop(0)


def test_mlx_reads_exact_32_by_24_frame() -> None:
    frame = [24.5] * THERMAL_PIXELS
    driver = MLX90640Driver(
        sensor_factory=lambda: FakeMlx(frame),
        max_retries=0,
        clock=ManualClock(),
    )
    driver.start()
    sample = driver.read()
    assert sample.values["width"] == 32
    assert sample.values["height"] == 24
    assert len(sample.values["temperatures_c"]) == 768


def test_mlx_rejects_nan_without_logging_matrix() -> None:
    frame = [24.5] * THERMAL_PIXELS
    frame[100] = math.nan
    driver = MLX90640Driver(
        sensor_factory=lambda: FakeMlx(frame),
        max_retries=0,
        clock=ManualClock(),
    )
    driver.start()
    with pytest.raises(SensorValidationError, match="1 invalid pixel"):
        driver.read()
    assert driver.invalid_frames == 1


@pytest.mark.parametrize(
    "frame",
    [
        [24.5] * (THERMAL_PIXELS - 1),
        [math.inf] + [24.5] * (THERMAL_PIXELS - 1),
        [-41.0] + [24.5] * (THERMAL_PIXELS - 1),
        [301.0] + [24.5] * (THERMAL_PIXELS - 1),
    ],
    ids=("short", "infinite", "below-range", "above-range"),
)
def test_mlx_rejects_corrupt_and_out_of_range_frames(frame: list[float]) -> None:
    driver = MLX90640Driver(
        sensor_factory=lambda: FakeMlx(frame),
        max_retries=0,
        clock=ManualClock(),
    )
    driver.start()

    with pytest.raises(SensorValidationError):
        driver.read()
    assert driver.invalid_frames == 1


def test_mlx_retries_invalid_frame_and_recovers_health() -> None:
    invalid = [24.5] * THERMAL_PIXELS
    invalid[10] = math.nan
    valid = [25.0] * THERMAL_PIXELS
    fake = SequencedFakeMlx([invalid, valid])
    driver = MLX90640Driver(
        sensor_factory=lambda: fake,
        max_retries=1,
        clock=ManualClock(),
    )
    driver.start()

    sample = driver.read()

    assert sample.values["temperatures_c"][10] == 25.0
    assert driver.invalid_frames == 1
    assert driver.health().failed_reads == 1
    assert driver.health().status.value == "ok"
