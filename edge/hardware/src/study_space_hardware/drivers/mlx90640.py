"""MLX90640 32 x 24 thermal-array driver.

The adapter uses the MIT-licensed Adafruit CircuitPython MLX90640 package as a
declared dependency instead of embedding a second copy of its low-level driver.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from .base import BaseSensorDriver, SensorStartError, SensorValidationError
from ..clock import Clock
from ..models import (
    SampleQuality,
    SensorSample,
    THERMAL_HEIGHT,
    THERMAL_PIXELS,
    THERMAL_WIDTH,
)


_REFRESH_NAMES = {
    0.5: "REFRESH_0_5_HZ",
    1.0: "REFRESH_1_HZ",
    2.0: "REFRESH_2_HZ",
    4.0: "REFRESH_4_HZ",
    8.0: "REFRESH_8_HZ",
    16.0: "REFRESH_16_HZ",
    32.0: "REFRESH_32_HZ",
    64.0: "REFRESH_64_HZ",
}


class MLX90640Driver(BaseSensorDriver):
    def __init__(
        self,
        *,
        sample_rate_hz: float = 2.0,
        i2c_frequency_hz: int = 800_000,
        address: int = 0x33,
        minimum_c: float = -40.0,
        maximum_c: float = 300.0,
        sensor_factory: Callable[[], Any] | None = None,
        max_retries: int = 2,
        offline_threshold: int = 3,
        clock: Clock | None = None,
    ) -> None:
        super().__init__(
            "thermal",
            sample_rate_hz=sample_rate_hz,
            max_retries=max_retries,
            offline_threshold=offline_threshold,
            clock=clock,
        )
        if minimum_c >= maximum_c:
            raise ValueError("minimum_c must be lower than maximum_c")
        self.i2c_frequency_hz = int(i2c_frequency_hz)
        self.address = int(address)
        self.minimum_c = float(minimum_c)
        self.maximum_c = float(maximum_c)
        self._sensor_factory = sensor_factory
        self._sensor: Any = None
        self._i2c: Any = None
        self.invalid_frames = 0

    def _start(self) -> None:
        if self._sensor_factory is not None:
            self._sensor = self._sensor_factory()
            return
        try:
            import adafruit_mlx90640
            import board
            import busio
        except ImportError as exc:
            raise SensorStartError(
                "MLX90640 dependencies are unavailable; install the 'hardware' "
                "extra on Raspberry Pi"
            ) from exc

        self._i2c = busio.I2C(
            board.SCL,
            board.SDA,
            frequency=self.i2c_frequency_hz,
        )
        self._sensor = adafruit_mlx90640.MLX90640(
            self._i2c,
            address=self.address,
        )
        refresh_name = _REFRESH_NAMES.get(self.sample_rate_hz)
        if refresh_name is None:
            raise SensorStartError(
                f"unsupported MLX90640 refresh rate: {self.sample_rate_hz}"
            )
        self._sensor.refresh_rate = getattr(
            adafruit_mlx90640.RefreshRate,
            refresh_name,
        )

    def _read(self) -> SensorSample:
        frame = [0.0] * THERMAL_PIXELS
        self._sensor.getFrame(frame)
        if len(frame) != THERMAL_PIXELS:
            self.invalid_frames += 1
            raise SensorValidationError(
                f"expected {THERMAL_PIXELS} thermal pixels, got {len(frame)}"
            )
        invalid = [
            index
            for index, value in enumerate(frame)
            if not math.isfinite(float(value))
            or not self.minimum_c <= float(value) <= self.maximum_c
        ]
        if invalid:
            self.invalid_frames += 1
            self._tracker.details["invalid_frames"] = self.invalid_frames
            self._tracker.details["last_invalid_pixel_count"] = len(invalid)
            raise SensorValidationError(
                f"thermal frame contains {len(invalid)} invalid pixel(s)"
            )

        captured_at = self.clock.now_utc()
        return SensorSample(
            sensor=self.name,
            captured_at=captured_at,
            monotonic_s=self.clock.monotonic(),
            values={
                "width": THERMAL_WIDTH,
                "height": THERMAL_HEIGHT,
                "temperatures_c": tuple(float(value) for value in frame),
            },
            units={"temperatures_c": "celsius"},
            quality=SampleQuality.VALID,
            source="mlx90640",
        )

    def _close(self) -> None:
        if self._i2c is not None and hasattr(self._i2c, "deinit"):
            self._i2c.deinit()
        self._i2c = None
        self._sensor = None
