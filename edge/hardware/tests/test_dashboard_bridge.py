from __future__ import annotations

from datetime import datetime, timezone

import pytest

from study_space_hardware.dashboard_bridge import (
    DashboardClient,
    LiveSnapshotBuilder,
    count_hot_regions,
    normalize_thermal,
)
from study_space_hardware.models import (
    SensorHealth,
    SensorHealthReport,
    SensorSample,
)


NOW = datetime(2026, 7, 22, 8, 30, tzinfo=timezone.utc)


def _sample(sensor: str, values: dict) -> SensorSample:
    return SensorSample(
        sensor=sensor,
        captured_at=NOW,
        monotonic_s=10.0,
        values=values,
        units={},
        source=f"test:{sensor}",
    )


def test_normalize_thermal_clips_and_preserves_shape() -> None:
    raw = [20.0 + index / 100 for index in range(768)]

    normalized = normalize_thermal(raw)

    assert len(normalized) == 768
    assert min(normalized) == 0.0
    assert max(normalized) == 1.0
    assert normalize_thermal([23.0] * 768) == [0.0] * 768
    with pytest.raises(ValueError, match="768"):
        normalize_thermal([20.0])


def test_hot_region_counter_uses_connected_components() -> None:
    values = [0.0] * 768
    values[33] = values[34] = values[35] = 0.9
    values[400] = values[432] = 0.8
    values[700] = 0.95

    assert count_hot_regions(values) == 2


def test_snapshot_builder_keeps_real_proxy_semantics() -> None:
    builder = LiveSnapshotBuilder(room_id="room_a", device_id="pi5-a")
    builder.accept(
        _sample(
            "thermal",
            {"width": 32, "height": 24, "temperatures_c": tuple(22 + index / 200 for index in range(768))},
        )
    )
    builder.accept(
        _sample(
            "sound",
            {"rms": 0.12, "peak": 0.31, "raw_audio_persisted": False},
        )
    )
    builder.accept(
        _sample(
            "light",
            {
                "light_adc_raw": 420,
                "light_normalized": 0.1026,
                "light_lux": None,
                "calibrated_lux": False,
                "warning": "hw486_uncalibrated_light_proxy",
            },
        )
    )
    builder.accept(
        _sample("climate", {"temperature_c": 23.6, "humidity_pct": 61.0})
    )
    reports = {
        name: SensorHealthReport(sensor=name, status=SensorHealth.OK)
        for name in ("thermal", "sound", "light", "climate")
    }

    bundle = builder.build(reports)
    preview = bundle["thermal_preview"]
    observation = bundle["observation"]

    assert preview["captured_at"] == "2026-07-22T08:30:00.000Z"
    assert preview["width"] == 32
    assert len(preview["values"]) == 768
    assert observation["room_state"] == "unknown"
    assert observation["occupancy_level"] == "unknown"
    assert observation["confidence"] == 0.0
    assert observation["features"]["sound_rms_mean"] == 0.12
    assert observation["features"]["light_lux"] is None
    assert observation["sensor_health"]["radar"] == "not_configured"
    assert observation["model"]["name"] == "sensor-dashboard-bridge"
    assert "hw486_uncalibrated_light_proxy" in observation["warnings"]
    assert "DASHBOARD_ONLY_NO_MODULE2_INFERENCE" in observation["warnings"]


def test_dashboard_client_requires_absolute_http_url() -> None:
    with pytest.raises(ValueError, match="absolute HTTP"):
        DashboardClient(backend_url="localhost:8000", room_id="room_a")
