from __future__ import annotations

import pytest

from study_space_hardware.clock import ManualClock
from study_space_hardware.drivers.base import SensorValidationError
from study_space_hardware.drivers.climate import ClimateDriver
from study_space_hardware.drivers.light import LightDriver


def test_light_driver_reads_lux_and_rejects_negative_values() -> None:
    driver = LightDriver(reader=lambda: 412.5, clock=ManualClock())
    driver.start()
    sample = driver.read()
    assert sample.values["light_lux"] == 412.5
    driver.close()

    invalid = LightDriver(
        reader=lambda: -1.0,
        max_retries=0,
        clock=ManualClock(),
    )
    invalid.start()
    with pytest.raises(SensorValidationError, match="invalid light level"):
        invalid.read()


def test_climate_driver_reads_standard_units_and_validates_ranges() -> None:
    driver = ClimateDriver(
        reader=lambda: (24.8, 61.0),
        clock=ManualClock(),
    )
    driver.start()
    sample = driver.read()
    assert sample.values["temperature_c"] == 24.8
    assert sample.values["humidity_pct"] == 61.0
    assert sample.units["temperature_c"] == "celsius"
    driver.close()

    invalid = ClimateDriver(
        reader=lambda: (24.8, 101.0),
        max_retries=0,
        clock=ManualClock(),
    )
    invalid.start()
    with pytest.raises(SensorValidationError, match="invalid humidity"):
        invalid.read()
