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
from .drivers.esp32_hub import (
    Esp32HubClimateDriver,
    Esp32HubLightDriver,
    Esp32HubRadarDriver,
    Esp32HubSoundDriver,
    Esp32HubThermalDriver,
    Esp32SerialHub,
)
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
    if config.transport.mode == "esp32_hub":
        return build_esp32_hub_drivers(config, clock)

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


def build_esp32_hub_drivers(
    config: HardwareConfig,
    clock: Clock,
) -> dict[str, SensorDriver]:
    """Build SensorDriver adapters sharing one ESP32 USB serial link."""

    transport = config.transport
    assert transport.port is not None
    hub = Esp32SerialHub(
        port=transport.port,
        baud_rate=transport.baud_rate,
        read_timeout_s=transport.read_timeout_s,
        reconnect_delay_s=transport.reconnect_delay_s,
        startup_timeout_s=transport.startup_timeout_s,
        queue_size=transport.queue_size,
        clock=clock,
    )
    drivers: dict[str, SensorDriver] = {}
    for name, settings in config.sensors.items():
        if not settings.enabled:
            continue
        common = {
            **_common(settings, clock),
            "hub": hub,
            "sample_timeout_s": transport.sample_timeout_s,
        }
        if name == "thermal":
            drivers[name] = Esp32HubThermalDriver(
                **common,
                minimum_c=float(settings.options.get("minimum_c", -40.0)),
                maximum_c=float(settings.options.get("maximum_c", 300.0)),
            )
        elif name == "radar":
            drivers[name] = Esp32HubRadarDriver(**common)
        elif name == "sound":
            drivers[name] = Esp32HubSoundDriver(**common)
        elif name == "light":
            drivers[name] = Esp32HubLightDriver(**common)
        elif name == "climate":
            drivers[name] = Esp32HubClimateDriver(**common)
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
