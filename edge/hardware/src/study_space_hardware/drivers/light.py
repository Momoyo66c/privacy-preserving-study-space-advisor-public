"""BH1750 light sensor adapter with injectable reader for tests."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from .base import BaseSensorDriver, SensorStartError, SensorValidationError
from ..clock import Clock
from ..models import SampleQuality, SensorSample


class LightDriver(BaseSensorDriver):
    def __init__(
        self,
        *,
        sample_rate_hz: float = 1.0,
        reader: Callable[[], float] | None = None,
        sensor_factory: Callable[[], Any] | None = None,
        max_retries: int = 1,
        offline_threshold: int = 3,
        clock: Clock | None = None,
    ) -> None:
        super().__init__(
            "light",
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
            import adafruit_bh1750
            import board
        except ImportError as exc:
            raise SensorStartError(
                "Adafruit BH1750 dependencies are unavailable"
            ) from exc
        self._i2c = board.I2C()
        self._sensor = adafruit_bh1750.BH1750(self._i2c)

    def _read(self) -> SensorSample:
        lux = float(self._reader() if self._reader else self._sensor.lux)
        if not math.isfinite(lux) or lux < 0:
            raise SensorValidationError(f"invalid light level: {lux}")
        return SensorSample(
            sensor=self.name,
            captured_at=self.clock.now_utc(),
            monotonic_s=self.clock.monotonic(),
            values={"light_lux": lux, "measurement_source": "bh1750"},
            units={"light_lux": "lux"},
            quality=SampleQuality.VALID,
            source="bh1750" if self._reader is None else "injected-light-reader",
        )

    def _close(self) -> None:
        if self._i2c is not None and hasattr(self._i2c, "deinit"):
            self._i2c.deinit()
        self._i2c = None
        self._sensor = None
