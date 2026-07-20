"""Configuration loading and validation."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


_ENV_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")
_SENSOR_NAMES = ("thermal", "radar", "sound", "light", "climate")
_TRANSPORT_MODES = ("direct", "esp32_hub")


@dataclass(frozen=True, slots=True)
class SensorSettings:
    enabled: bool = True
    sample_rate_hz: float = 1.0
    max_retries: int = 1
    offline_threshold: int = 3
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StorageSettings:
    data_dir: str = "data/sessions"
    retention_days: int = 30
    max_sessions: int = 100


@dataclass(frozen=True, slots=True)
class SimulatorSettings:
    enabled: bool = True
    scenario: str = "quiet_study_recommended"
    random_seed: int = 3025


@dataclass(frozen=True, slots=True)
class TransportSettings:
    mode: str = "direct"
    port: str | None = None
    baud_rate: int = 460_800
    read_timeout_s: float = 0.05
    reconnect_delay_s: float = 0.25
    startup_timeout_s: float = 2.0
    sample_timeout_s: float = 0.75
    queue_size: int = 64


@dataclass(frozen=True, slots=True)
class ActuationSettings:
    device: str = "log"
    buzzer_enabled: bool = False
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HardwareConfig:
    room_id: str
    device_id: str
    window_seconds: float = 5.0
    sensors: Mapping[str, SensorSettings] = field(default_factory=dict)
    storage: StorageSettings = field(default_factory=StorageSettings)
    simulator: SimulatorSettings = field(default_factory=SimulatorSettings)
    transport: TransportSettings = field(default_factory=TransportSettings)
    actuation: ActuationSettings = field(default_factory=ActuationSettings)

    def validate(self) -> None:
        if not self.room_id or not self.room_id.isascii():
            raise ValueError("room_id must be a non-empty ASCII string")
        if not self.device_id or not self.device_id.isascii():
            raise ValueError("device_id must be a non-empty ASCII string")
        if not 5.0 <= self.window_seconds <= 10.0:
            raise ValueError("window_seconds must be between 5 and 10")
        unknown = set(self.sensors) - set(_SENSOR_NAMES)
        if unknown:
            raise ValueError(f"unknown sensors: {sorted(unknown)}")
        for name, sensor in self.sensors.items():
            if sensor.sample_rate_hz <= 0:
                raise ValueError(f"{name}.sample_rate_hz must be positive")
            if sensor.max_retries < 0:
                raise ValueError(f"{name}.max_retries cannot be negative")
            if sensor.offline_threshold < 1:
                raise ValueError(f"{name}.offline_threshold must be at least 1")
        if self.storage.retention_days < 1 or self.storage.max_sessions < 1:
            raise ValueError("storage retention values must be positive")
        if self.transport.mode not in _TRANSPORT_MODES:
            raise ValueError(
                f"transport.mode must be one of {list(_TRANSPORT_MODES)}"
            )
        if self.transport.mode == "esp32_hub" and not self.transport.port:
            raise ValueError("transport.port is required for esp32_hub mode")
        if self.transport.baud_rate <= 0:
            raise ValueError("transport.baud_rate must be positive")
        if self.transport.read_timeout_s <= 0:
            raise ValueError("transport.read_timeout_s must be positive")
        if self.transport.reconnect_delay_s < 0:
            raise ValueError("transport.reconnect_delay_s cannot be negative")
        if self.transport.startup_timeout_s <= 0:
            raise ValueError("transport.startup_timeout_s must be positive")
        if self.transport.sample_timeout_s <= 0:
            raise ValueError("transport.sample_timeout_s must be positive")
        if self.transport.queue_size < 1:
            raise ValueError("transport.queue_size must be at least 1")
        if self.actuation.buzzer_enabled:
            raise ValueError(
                "buzzer_enabled must remain false by default; enable only in an "
                "explicit demonstration configuration"
            )


def _expand_environment(value: Any) -> Any:
    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in os.environ:
                raise ValueError(f"missing environment variable: {name}")
            return os.environ[name]

        return _ENV_PATTERN.sub(replace, value)
    if isinstance(value, list):
        return [_expand_environment(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_environment(item) for key, item in value.items()}
    return value


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return dict(value)


def config_from_dict(raw: Mapping[str, Any]) -> HardwareConfig:
    data = _expand_environment(dict(raw))
    sensor_data = _mapping(data.get("sensors"), "sensors")
    sensors: dict[str, SensorSettings] = {}
    for name in _SENSOR_NAMES:
        current = _mapping(sensor_data.get(name), f"sensors.{name}")
        options = _mapping(current.pop("options", {}), f"sensors.{name}.options")
        sensors[name] = SensorSettings(options=options, **current)

    config = HardwareConfig(
        room_id=str(data.get("room_id", "")),
        device_id=str(data.get("device_id", "")),
        window_seconds=float(data.get("window_seconds", 5.0)),
        sensors=sensors,
        storage=StorageSettings(**_mapping(data.get("storage"), "storage")),
        simulator=SimulatorSettings(
            **_mapping(data.get("simulator"), "simulator")
        ),
        transport=TransportSettings(
            **_mapping(data.get("transport"), "transport")
        ),
        actuation=ActuationSettings(
            **_mapping(data.get("actuation"), "actuation")
        ),
    )
    config.validate()
    return config


def load_config(path: str | Path) -> HardwareConfig:
    config_path = Path(path)
    suffix = config_path.suffix.lower()
    with config_path.open("rb") as handle:
        if suffix == ".toml":
            raw = tomllib.load(handle)
        elif suffix in {".yaml", ".yml"}:
            try:
                import yaml
            except ImportError as exc:
                raise RuntimeError(
                    "PyYAML is required for YAML configuration; install the package "
                    "or use TOML"
                ) from exc
            raw = yaml.safe_load(handle) or {}
        else:
            raise ValueError("configuration must use .yaml, .yml, or .toml")
    if not isinstance(raw, dict):
        raise ValueError("configuration root must be a mapping")
    return config_from_dict(raw)
