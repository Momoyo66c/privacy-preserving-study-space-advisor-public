"""AHT20/AHTx0 temperature and humidity adapter."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from .base import BaseSensorDriver, SensorStartError, SensorValidationError
from ..clock import Clock
from ..models import SampleQuality, SensorSample


class ClimateDriver(BaseSensorDriver):
    def __init__(
        self,
        *,
        sample_rate_hz: float = 1.0,
        reader: Callable[[], tuple[float, float]] | None = None,
        sensor_factory: Callable[[], Any] | None = None,
        max_retries: int = 1,
        offline_threshold: int = 3,
        clock: Clock | None = None,
    ) -> None:
        super().__init__(
            "climate",
            sample_rate_hz=sample_rate_hz,
            max_retries=max_retries,
            offline_threshold=offline_threshold,
            clock=clock,
        )
        self._reader = reader
        self._sensor_factory = sensor_factory
        self._sensor: Any = None
        self._i2c: Any = None

    def _start(self) -> None:
        if self._reader is not None:
            return
        if self._sensor_factory is not None:
            self._sensor = self._sensor_factory()
            return
        try:
            import adafruit_ahtx0
            import board
        except ImportError as exc:
            raise SensorStartError(
                "Adafruit AHTx0 dependencies are unavailable"
            ) from exc
        self._i2c = board.I2C()
        self._sensor = adafruit_ahtx0.AHTx0(self._i2c)

    def _read(self) -> SensorSample:
        if self._reader is not None:
            temperature_c, humidity_pct = self._reader()
        else:
            temperature_c = self._sensor.temperature
            humidity_pct = self._sensor.relative_humidity
        temperature_c = float(temperature_c)
        humidity_pct = float(humidity_pct)
        if not math.isfinite(temperature_c) or not -40 <= temperature_c <= 125:
            raise SensorValidationError(
                f"invalid temperature reading: {temperature_c}"
            )
        if not math.isfinite(humidity_pct) or not 0 <= humidity_pct <= 100:
            raise SensorValidationError(
                f"invalid humidity reading: {humidity_pct}"
            )
        return SensorSample(
            sensor=self.name,
            captured_at=self.clock.now_utc(),
            monotonic_s=self.clock.monotonic(),
            values={
                "temperature_c": temperature_c,
                "humidity_pct": humidity_pct,
                "measurement_source": "ahtx0",
            },
            units={
                "temperature_c": "celsius",
                "humidity_pct": "percent_relative_humidity",
            },
            quality=SampleQuality.VALID,
            source="ahtx0" if self._reader is None else "injected-climate-reader",
        )

    def _close(self) -> None:
        if self._i2c is not None and hasattr(self._i2c, "deinit"):
            self._i2c.deinit()
        self._i2c = None
        self._sensor = None
