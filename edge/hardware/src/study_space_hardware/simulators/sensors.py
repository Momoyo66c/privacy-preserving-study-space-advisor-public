"""Simulated drivers that use the same interface and validation path as hardware."""

from __future__ import annotations

import math
import random
from typing import Any

from ..clock import Clock
from ..config import HardwareConfig
from ..drivers.base import BaseSensorDriver, SensorReadError
from ..models import (
    RadarTarget,
    SampleQuality,
    SensorSample,
    THERMAL_HEIGHT,
    THERMAL_WIDTH,
)
from .scenario import ScenarioName, ScenarioProfile, get_profile


_SENSOR_SEED_OFFSETS = {
    "thermal": 101,
    "radar": 211,
    "sound": 307,
    "light": 401,
    "climate": 503,
}


class SimulatedSensorDriver(BaseSensorDriver):
    def __init__(
        self,
        sensor_name: str,
        *,
        scenario: str | ScenarioName,
        random_seed: int,
        sample_rate_hz: float,
        max_retries: int,
        offline_threshold: int,
        clock: Clock,
    ) -> None:
        super().__init__(
            sensor_name,
            sample_rate_hz=sample_rate_hz,
            max_retries=max_retries,
            retry_delay_s=0.001,
            offline_threshold=offline_threshold,
            clock=clock,
        )
        self.scenario = ScenarioName(scenario)
        self.profile: ScenarioProfile = get_profile(self.scenario)
        self.random = random.Random(
            random_seed + _SENSOR_SEED_OFFSETS[sensor_name]
        )
        self.index = 0

    def _read(self) -> SensorSample:
        self.index += 1
        self._maybe_fail()
        values, units = getattr(self, f"_read_{self.name}")()
        return SensorSample(
            sensor=self.name,
            captured_at=self.clock.now_utc(),
            monotonic_s=self.clock.monotonic(),
            values=values,
            units=units,
            quality=SampleQuality.VALID,
            source=f"simulator:{self.scenario.value}",
        )

    def _maybe_fail(self) -> None:
        if (
            self.scenario is ScenarioName.DEGRADED_THERMAL
            and self.name == "thermal"
        ):
            raise SensorReadError("simulated thermal sensor is offline")
        if self.scenario is ScenarioName.DEGRADED_RADAR and self.name == "radar":
            raise SensorReadError("simulated radar sensor is offline")
        if self.scenario is ScenarioName.INTERMITTENT_FAILURE:
            periods = {"thermal": 7, "radar": 5, "sound": 11}
            period = periods.get(self.name)
            if period and self.index % period == 0:
                raise SensorReadError(
                    f"simulated intermittent {self.name} failure"
                )

    def _read_thermal(self) -> tuple[dict[str, Any], dict[str, str]]:
        base = 23.0 + 0.15 * math.sin(self.index / 4)
        hotspot_centres = [
            (
                (5 + spot * 6 + self.index // 3) % THERMAL_WIDTH,
                (6 + spot * 4) % THERMAL_HEIGHT,
            )
            for spot in range(self.profile.thermal_hotspots)
        ]
        frame: list[float] = []
        for y in range(THERMAL_HEIGHT):
            for x in range(THERMAL_WIDTH):
                value = base + self.random.gauss(0, 0.08)
                for centre_x, centre_y in hotspot_centres:
                    distance_sq = (x - centre_x) ** 2 + (y - centre_y) ** 2
                    value += 8.0 * math.exp(-distance_sq / 5.0)
                frame.append(round(value, 3))
        return (
            {
                "width": THERMAL_WIDTH,
                "height": THERMAL_HEIGHT,
                "temperatures_c": tuple(frame),
            },
            {"temperatures_c": "celsius"},
        )

    def _read_radar(self) -> tuple[dict[str, Any], dict[str, str]]:
        targets: list[RadarTarget] = []
        for slot in range(3):
            valid = slot < self.profile.radar_targets
            if valid:
                phase = self.index / 3 + slot
                x_mm = int((slot - 1) * 850 + 120 * math.sin(phase))
                y_mm = int(1500 + slot * 700 + 90 * math.cos(phase))
                speed = int(10 + 25 * math.sin(phase * 1.7))
                resolution = 120 + slot * 20
            else:
                x_mm = y_mm = speed = resolution = 0
            targets.append(
                RadarTarget(
                    slot=slot,
                    x_mm=x_mm,
                    y_mm=y_mm,
                    speed_cm_s=speed,
                    distance_resolution_mm=resolution,
                    valid=valid,
                )
            )
        return (
            {"targets": tuple(targets)},
            {
                "x_mm": "millimetres",
                "y_mm": "millimetres",
                "speed_cm_s": "centimetres_per_second",
                "distance_resolution_mm": "millimetres",
            },
        )

    def _read_sound(self) -> tuple[dict[str, Any], dict[str, str]]:
        rms = max(0.0, self.profile.sound_rms + self.random.gauss(0, 0.015))
        return (
            {
                "rms": round(rms, 5),
                "std": round(rms * (0.18 + self.random.random() * 0.08), 5),
                "peak": round(min(1.0, rms * (1.5 + self.random.random())), 5),
                "raw_audio_persisted": False,
                "chunk_frames": 800,
            },
            {"rms": "normalized", "std": "normalized", "peak": "normalized"},
        )

    def _read_light(self) -> tuple[dict[str, Any], dict[str, str]]:
        lux = self.profile.light_lux + 8 * math.sin(self.index / 5)
        lux += self.random.gauss(0, 2)
        return (
            {
                "light_lux": round(max(0.0, lux), 2),
                "measurement_source": "simulator",
            },
            {"light_lux": "lux"},
        )

    def _read_climate(self) -> tuple[dict[str, Any], dict[str, str]]:
        temperature = self.profile.temperature_c + 0.1 * math.sin(self.index / 8)
        humidity = self.profile.humidity_pct + 0.3 * math.cos(self.index / 9)
        return (
            {
                "temperature_c": round(temperature, 3),
                "humidity_pct": round(humidity, 3),
                "measurement_source": "simulator",
            },
            {
                "temperature_c": "celsius",
                "humidity_pct": "percent_relative_humidity",
            },
        )


def build_simulated_drivers(
    config: HardwareConfig,
    clock: Clock,
) -> dict[str, SimulatedSensorDriver]:
    drivers: dict[str, SimulatedSensorDriver] = {}
    for name, settings in config.sensors.items():
        if not settings.enabled:
            continue
        drivers[name] = SimulatedSensorDriver(
            name,
            scenario=config.simulator.scenario,
            random_seed=config.simulator.random_seed,
            sample_rate_hz=settings.sample_rate_hz,
            max_retries=settings.max_retries,
            offline_threshold=settings.offline_threshold,
            clock=clock,
        )
    return drivers
