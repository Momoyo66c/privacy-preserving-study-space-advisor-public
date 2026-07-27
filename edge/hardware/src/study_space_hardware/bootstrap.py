"""Construct simulator or real-hardware runtime components from configuration."""

from __future__ import annotations

import os
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
from .drivers.remote_sound import RemoteSoundFeatureDriver
from .drivers.sound_level import SoundLevelDriver
from .orchestrator import SensorOrchestrator
from .relative_light import load_calibration
from .relative_sound import load_calibration as load_sound_calibration
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
        if name == "sound" and settings.options.get("driver") == "remote_feature":
            token_env = str(
                settings.options.get("token_env", "PSSA_REMOTE_SOUND_TOKEN")
            )
            bearer_token = os.environ.get(token_env, "")
            if not bearer_token:
                raise ValueError(
                    f"missing remote sound bearer token environment variable: "
                    f"{token_env}"
                )
            drivers[name] = RemoteSoundFeatureDriver(
                **_common(settings, clock),
                room_id=config.room_id,
                expected_device_id=str(
                    settings.options.get(
                        "expected_device_id",
                        "windows-laptop-mic",
                    )
                ),
                bearer_token=bearer_token,
                listen_host=str(
                    settings.options.get("listen_host", "127.0.0.1")
                ),
                listen_port=int(settings.options.get("listen_port", 8766)),
                max_feature_age_s=float(
                    settings.options.get("max_feature_age_s", 4.0)
                ),
                max_future_skew_s=float(
                    settings.options.get("max_future_skew_s", 2.0)
                ),
                offline_after_s=float(
                    settings.options.get("offline_after_s", 8.0)
                ),
                max_body_bytes=int(
                    settings.options.get("max_body_bytes", 4096)
                ),
            )
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
            driver_kind = settings.options.get("driver", "esp32_hub")
            if driver_kind != "esp32_hub":
                raise ValueError(
                    f"unsupported ESP32 hub sound driver: {driver_kind}"
                )
            calibration_path = settings.options.get(
                "relative_calibration_path"
            ) or os.environ.get("HW485_RELATIVE_CALIBRATION_PATH")
            calibration = (
                load_sound_calibration(
                    str(calibration_path),
                    expected_device_id=config.device_id,
                )
                if calibration_path
                else None
            )
            drivers[name] = Esp32HubSoundDriver(
                **common,
                relative_calibration=calibration,
            )
        elif name == "light":
            calibration_path = settings.options.get(
                "relative_calibration_path"
            ) or os.environ.get("HW486_RELATIVE_CALIBRATION_PATH")
            calibration = (
                load_calibration(
                    str(calibration_path),
                    expected_device_id=config.device_id,
                )
                if calibration_path
                else None
            )
            drivers[name] = Esp32HubLightDriver(
                **common,
                relative_calibration=calibration,
            )
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
