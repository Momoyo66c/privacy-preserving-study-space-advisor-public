"""Construct simulator or real-hardware runtime components from configuration."""

from __future__ import annotations

from typing import Any

from .actuation.base import LoggingStatusIndicator, StatusIndicator
from .actuation.gpio_led import GpioRgbLedIndicator
from .actuation.microbit import MicrobitSerialIndicator
from .clock import Clock, SystemClock
from .config import HardwareConfig, SensorSettings
from .drivers.base import SensorDriver
from .drivers.climate import ClimateDriver
from .drivers.ld2450 import LD2450Driver
from .drivers.light import LightDriver
from .drivers.mlx90640 import MLX90640Driver
from .drivers.sound_level import SoundLevelDriver
from .orchestrator import SensorOrchestrator
from .simulators.sensors import build_simulated_drivers


def _common(settings: SensorSettings, clock: Clock) -> dict[str, Any]:
    return {
        "sample_rate_hz": settings.sample_rate_hz,
        "max_retries": settings.max_retries,
        "offline_threshold": settings.offline_threshold,
        "clock": clock,
    }


def build_real_drivers(
    config: HardwareConfig,
    clock: Clock,
) -> dict[str, SensorDriver]:
    drivers: dict[str, SensorDriver] = {}
    for name, settings in config.sensors.items():
        if not settings.enabled:
            continue
        options = dict(settings.options)
        common = _common(settings, clock)
        if name == "thermal":
            drivers[name] = MLX90640Driver(**common, **options)
        elif name == "radar":
            drivers[name] = LD2450Driver(**common, **options)
        elif name == "sound":
            drivers[name] = SoundLevelDriver(**common, **options)
        elif name == "light":
            drivers[name] = LightDriver(**common, **options)
        elif name == "climate":
            drivers[name] = ClimateDriver(**common, **options)
    return drivers


def build_status_indicator(config: HardwareConfig) -> StatusIndicator:
    device = config.actuation.device
    options = dict(config.actuation.options)
    if device in {"none", "log"}:
        return LoggingStatusIndicator()
    if device == "gpio_rgb":
        return GpioRgbLedIndicator(**options)
    if device == "microbit":
        return MicrobitSerialIndicator(**options)
    raise ValueError(f"unsupported actuation device: {device}")


def build_orchestrator(
    config: HardwareConfig,
    *,
    clock: Clock | None = None,
) -> SensorOrchestrator:
    clock = clock or SystemClock()
    drivers = (
        build_simulated_drivers(config, clock)
        if config.simulator.enabled
        else build_real_drivers(config, clock)
    )
    return SensorOrchestrator(
        room_id=config.room_id,
        device_id=config.device_id,
        window_seconds=config.window_seconds,
        drivers=drivers,
        clock=clock,
        status_indicator=build_status_indicator(config),
    )
