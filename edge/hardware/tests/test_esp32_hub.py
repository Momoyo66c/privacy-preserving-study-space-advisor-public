from __future__ import annotations

import math
import queue
import struct
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

import pytest

from study_space_hardware.bootstrap import build_real_drivers
from study_space_hardware.clock import ManualClock
from study_space_hardware.config import config_from_dict
from study_space_hardware.drivers.base import SensorReadError, SensorValidationError
from study_space_hardware.drivers.esp32_hub import (
    Esp32HubClimateDriver,
    Esp32HubLightDriver,
    Esp32HubRadarDriver,
    Esp32HubSoundDriver,
    Esp32HubThermalDriver,
    Esp32SerialHub,
    ReceivedHubFrame,
)
from study_space_hardware.drivers.ld2450 import REPORT_HEADER, REPORT_TAIL
from study_space_hardware.esp32_protocol import MessageType, ProtocolFrame, encode_frame
from study_space_hardware.models import THERMAL_PIXELS
from study_space_hardware.orchestrator import SensorOrchestrator


NOW = datetime(2026, 7, 20, 7, 0, tzinfo=timezone.utc)


def _received(message_type: MessageType, payload: bytes) -> ReceivedHubFrame:
    return ReceivedHubFrame(
        frame=ProtocolFrame(
            message_type=message_type,
            sequence=7,
            device_uptime_ms=5_000,
            payload=payload,
        ),
        received_at=NOW,
        received_monotonic_s=10.0,
    )


class StubHub:
    def __init__(self, frames: list[ReceivedHubFrame]) -> None:
        self.frames = deque(frames)
        self.acquired: list[str] = []
        self.released: list[str] = []

    def acquire(self, client: str) -> None:
        self.acquired.append(client)

    def release(self, client: str) -> None:
        self.released.append(client)

    def read_frame(
        self,
        message_type: int | MessageType,
        *,
        timeout_s: float,
    ) -> ReceivedHubFrame:
        del timeout_s
        if not self.frames:
            raise SensorReadError("stub queue is empty")
        frame = self.frames.popleft()
        assert frame.frame.message_type == int(message_type)
        return frame

    def diagnostics(self) -> dict[str, Any]:
        return {
            "sequence_gaps": 0,
            "queue_drops": 0,
            "reconnects": 0,
            "protocol_invalid_frames": 0,
        }


class QueueSerial:
    def __init__(self) -> None:
        self.input: queue.Queue[bytes | Exception] = queue.Queue()
        self.closed = False

    def push(self, value: bytes | Exception) -> None:
        self.input.put(value)

    def read(self, size: int) -> bytes:
        del size
        if self.closed:
            raise OSError("serial port closed")
        try:
            value = self.input.get(timeout=0.01)
        except queue.Empty:
            return b""
        if isinstance(value, Exception):
            raise value
        return value

    def close(self) -> None:
        self.closed = True


def _wait_for(predicate: Any, timeout_s: float = 1.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("condition did not become true before timeout")
        time.sleep(0.005)


def _thermal_payload(value_centi_c: int = 2450) -> bytes:
    return bytes((32, 24)) + struct.pack(
        f"<{THERMAL_PIXELS}h",
        *([value_centi_c] * THERMAL_PIXELS),
    )


def _radar_payload() -> bytes:
    target = (
        (100).to_bytes(2, "little")
        + (200).to_bytes(2, "little")
        + (10).to_bytes(2, "little")
        + (50).to_bytes(2, "little")
    )
    return REPORT_HEADER + target + (b"\x00" * 16) + REPORT_TAIL


def _light_payload(
    adc_raw: int = 2048,
    normalized: float = 0.5,
    calibrated_lux: float = 0.0,
    flags: int = 0,
) -> bytes:
    return struct.pack("<HffB", adc_raw, normalized, calibrated_lux, flags)


def test_hub_thermal_driver_preserves_existing_sample_shape() -> None:
    hub = StubHub([_received(MessageType.THERMAL, _thermal_payload())])
    driver = Esp32HubThermalDriver(
        hub=hub,  # type: ignore[arg-type]
        max_retries=0,
        clock=ManualClock(),
    )
    driver.start()
    sample = driver.read()
    driver.close()

    assert sample.captured_at == NOW
    assert sample.monotonic_s == 10.0
    assert sample.values["width"] == 32
    assert sample.values["height"] == 24
    assert sample.values["temperatures_c"] == (24.5,) * THERMAL_PIXELS
    assert sample.source == "esp32-hub:mlx90640"
    assert hub.acquired == ["thermal"]
    assert hub.released == ["thermal"]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"\x20", "shorter than dimensions"),
        (bytes((31, 24)) + b"x" * 10, "expected 32x24"),
        (_thermal_payload()[:-2], "thermal payload bytes"),
        (_thermal_payload(-4100), "invalid pixel"),
        (_thermal_payload(30100), "invalid pixel"),
    ],
)
def test_hub_thermal_driver_rejects_invalid_payloads(
    payload: bytes,
    message: str,
) -> None:
    hub = StubHub([_received(MessageType.THERMAL, payload)])
    driver = Esp32HubThermalDriver(
        hub=hub,  # type: ignore[arg-type]
        max_retries=0,
        clock=ManualClock(),
    )
    driver.start()
    with pytest.raises(SensorValidationError, match=message):
        driver.read()


def test_hub_radar_driver_reuses_ld2450_parser() -> None:
    hub = StubHub([_received(MessageType.RADAR, _radar_payload())])
    driver = Esp32HubRadarDriver(
        hub=hub,  # type: ignore[arg-type]
        max_retries=0,
        clock=ManualClock(),
    )
    driver.start()
    sample = driver.read()

    targets = sample.values["targets"]
    assert targets[0].x_mm == 100
    assert targets[0].y_mm == 200
    assert targets[0].speed_cm_s == 10
    assert sample.source == "esp32-hub:hlk-ld2450"


@pytest.mark.parametrize(
    "payload",
    [
        b"short",
        b"\x00" * 30,
        REPORT_HEADER + (b"\x00" * 24) + b"bad",
    ],
)
def test_hub_radar_driver_rejects_invalid_reports(payload: bytes) -> None:
    hub = StubHub([_received(MessageType.RADAR, payload)])
    driver = Esp32HubRadarDriver(
        hub=hub,  # type: ignore[arg-type]
        max_retries=0,
        clock=ManualClock(),
    )
    driver.start()
    with pytest.raises(SensorValidationError):
        driver.read()


def test_hub_sound_driver_never_exposes_raw_audio() -> None:
    payload = struct.pack("<fffH", 0.2, 0.05, 0.4, 400)
    hub = StubHub([_received(MessageType.SOUND, payload)])
    driver = Esp32HubSoundDriver(
        hub=hub,  # type: ignore[arg-type]
        max_retries=0,
        clock=ManualClock(),
    )
    driver.start()
    sample = driver.read()

    assert sample.values["raw_audio_persisted"] is False
    assert sample.values["chunk_frames"] == 400
    assert set(sample.values) == {
        "rms",
        "std",
        "peak",
        "raw_audio_persisted",
        "chunk_frames",
    }
    assert driver.raw_audio_persisted is False
    assert sample.source == "esp32-hub:hw485-relative-sound"


@pytest.mark.parametrize(
    "payload",
    [
        b"short",
        struct.pack("<fffH", math.nan, 0.1, 0.2, 800),
        struct.pack("<fffH", -0.1, 0.1, 0.2, 800),
        struct.pack("<fffH", 1.1, 0.1, 0.2, 800),
        struct.pack("<fffH", 0.1, 0.1, 0.2, 0),
    ],
)
def test_hub_sound_driver_rejects_invalid_statistics(payload: bytes) -> None:
    hub = StubHub([_received(MessageType.SOUND, payload)])
    driver = Esp32HubSoundDriver(
        hub=hub,  # type: ignore[arg-type]
        max_retries=0,
        clock=ManualClock(),
    )
    driver.start()
    with pytest.raises(SensorValidationError):
        driver.read()


def test_hub_environment_drivers_preserve_units_and_sources() -> None:
    light_hub = StubHub([_received(MessageType.LIGHT, _light_payload())])
    light = Esp32HubLightDriver(
        hub=light_hub,  # type: ignore[arg-type]
        max_retries=0,
        clock=ManualClock(),
    )
    light.start()
    light_sample = light.read()

    climate_hub = StubHub(
        [_received(MessageType.CLIMATE, struct.pack("<ff", 24.5, 61.0))]
    )
    climate = Esp32HubClimateDriver(
        hub=climate_hub,  # type: ignore[arg-type]
        max_retries=0,
        clock=ManualClock(),
    )
    climate.start()
    climate_sample = climate.read()

    assert light_sample.values["light_adc_raw"] == 2048
    assert light_sample.values["light_normalized"] == pytest.approx(0.5)
    assert light_sample.values["light_lux"] is None
    assert light_sample.values["calibrated_lux"] is False
    assert light_sample.values["warning"] == "hw486_uncalibrated_light_proxy"
    assert light_sample.units["light_lux"] == "lux"
    assert light_sample.source == "esp32-hub:hw486-ldr-proxy"
    assert climate_sample.values["temperature_c"] == pytest.approx(24.5)
    assert climate_sample.values["humidity_pct"] == pytest.approx(61.0)
    assert climate_sample.units["humidity_pct"] == "percent_relative_humidity"
    assert climate_sample.values["measurement_source"] == "dht11"
    assert climate_sample.source == "esp32-hub:dht11"


def test_hub_light_driver_accepts_explicit_calibration_flag() -> None:
    hub = StubHub(
        [_received(MessageType.LIGHT, _light_payload(3000, 0.75, 420.5, 1))]
    )
    driver = Esp32HubLightDriver(
        hub=hub,  # type: ignore[arg-type]
        max_retries=0,
        clock=ManualClock(),
    )
    driver.start()
    sample = driver.read()

    assert sample.values["light_lux"] == pytest.approx(420.5)
    assert sample.values["calibrated_lux"] is True
    assert "warning" not in sample.values


@pytest.mark.parametrize(
    ("driver_type", "message_type", "payload"),
    [
        (Esp32HubLightDriver, MessageType.LIGHT, _light_payload(4096)),
        (
            Esp32HubLightDriver,
            MessageType.LIGHT,
            _light_payload(2000, math.nan),
        ),
        (Esp32HubLightDriver, MessageType.LIGHT, _light_payload(2000, 1.1)),
        (Esp32HubLightDriver, MessageType.LIGHT, _light_payload(flags=2)),
        (
            Esp32HubLightDriver,
            MessageType.LIGHT,
            _light_payload(calibrated_lux=-1.0, flags=1),
        ),
        (Esp32HubLightDriver, MessageType.LIGHT, b"short"),
        (
            Esp32HubClimateDriver,
            MessageType.CLIMATE,
            struct.pack("<ff", 126.0, 50.0),
        ),
        (
            Esp32HubClimateDriver,
            MessageType.CLIMATE,
            struct.pack("<ff", 20.0, 101.0),
        ),
        (Esp32HubClimateDriver, MessageType.CLIMATE, b"short"),
    ],
)
def test_hub_environment_drivers_reject_invalid_payloads(
    driver_type: type[Esp32HubLightDriver] | type[Esp32HubClimateDriver],
    message_type: MessageType,
    payload: bytes,
) -> None:
    hub = StubHub([_received(message_type, payload)])
    driver = driver_type(
        hub=hub,  # type: ignore[arg-type]
        max_retries=0,
        clock=ManualClock(),
    )
    driver.start()
    with pytest.raises(SensorValidationError):
        driver.read()


def test_serial_hub_demultiplexes_chunks_and_reports_sequence_gaps() -> None:
    serial_port = QueueSerial()
    hub = Esp32SerialHub(
        port="/dev/test-esp32",
        startup_timeout_s=0.5,
        reconnect_delay_s=0.01,
        serial_factory=lambda: serial_port,
    )
    hub.acquire("test")
    heartbeat = ProtocolFrame(
        message_type=MessageType.HEARTBEAT,
        sequence=1,
        device_uptime_ms=100,
        payload=struct.pack("<II", 0x1F, 3),
    )
    thermal = ProtocolFrame(
        message_type=MessageType.THERMAL,
        sequence=3,
        device_uptime_ms=200,
        payload=_thermal_payload(),
    )
    wire = encode_frame(heartbeat) + encode_frame(thermal)
    serial_port.push(wire[:7])
    serial_port.push(wire[7:])

    received = hub.read_frame(MessageType.THERMAL, timeout_s=0.5)
    diagnostics = hub.diagnostics()
    hub.release("test")

    assert received.frame == thermal
    assert diagnostics["sequence_gaps"] == 1
    assert diagnostics["device_dropped_samples"] == 3
    assert diagnostics["protocol_decoded_frames"] == 2
    assert serial_port.closed is True


def test_serial_hub_bounds_queues_and_ignores_duplicate_frames() -> None:
    serial_port = QueueSerial()
    hub = Esp32SerialHub(
        port="/dev/test-esp32",
        queue_size=2,
        startup_timeout_s=0.5,
        serial_factory=lambda: serial_port,
    )
    hub.acquire("test")
    frames = [
        ProtocolFrame(
            message_type=MessageType.LIGHT,
            sequence=sequence,
            device_uptime_ms=sequence * 10,
            payload=struct.pack("<f", float(sequence)),
        )
        for sequence in (1, 2, 3)
    ]
    serial_port.push(b"".join(encode_frame(frame) for frame in frames))
    serial_port.push(encode_frame(frames[-1]))
    _wait_for(lambda: hub.diagnostics()["protocol_decoded_frames"] == 4)

    first = hub.read_frame(MessageType.LIGHT, timeout_s=0.2)
    second = hub.read_frame(MessageType.LIGHT, timeout_s=0.2)
    diagnostics = hub.diagnostics()
    hub.release("test")

    assert (first.frame.sequence, second.frame.sequence) == (2, 3)
    assert diagnostics["queue_drops"] == 1
    assert diagnostics["duplicates"] == 1


def test_serial_hub_fails_fast_for_unadvertised_sensor() -> None:
    serial_port = QueueSerial()
    hub = Esp32SerialHub(
        port="/dev/test-esp32",
        startup_timeout_s=0.5,
        serial_factory=lambda: serial_port,
    )
    hub.acquire("test")
    heartbeat = ProtocolFrame(
        message_type=MessageType.HEARTBEAT,
        sequence=1,
        device_uptime_ms=100,
        payload=struct.pack("<II", 1 << 3, 0),
    )
    serial_port.push(encode_frame(heartbeat))
    _wait_for(lambda: hub.diagnostics()["frames_received"] == 1)

    with pytest.raises(SensorReadError, match="does not advertise"):
        hub.read_frame(MessageType.THERMAL, timeout_s=0.5)
    hub.release("test")


def test_serial_hub_clears_stale_queue_when_sensor_goes_offline() -> None:
    serial_port = QueueSerial()
    hub = Esp32SerialHub(
        port="/dev/test-esp32",
        startup_timeout_s=0.5,
        serial_factory=lambda: serial_port,
    )
    hub.acquire("test")
    light = ProtocolFrame(
        message_type=MessageType.LIGHT,
        sequence=1,
        device_uptime_ms=100,
        payload=struct.pack("<f", 321.0),
    )
    offline = ProtocolFrame(
        message_type=MessageType.HEALTH,
        sequence=2,
        device_uptime_ms=110,
        payload=struct.pack("<BBHI", MessageType.LIGHT, 2, 7, 1),
    )
    serial_port.push(encode_frame(light) + encode_frame(offline))
    _wait_for(lambda: hub.diagnostics()["frames_received"] == 2)

    with pytest.raises(SensorReadError, match="reports this sensor offline"):
        hub.read_frame(MessageType.LIGHT, timeout_s=0.5)
    assert hub.diagnostics()["queue_drops"] == 1
    hub.release("test")


def test_serial_hub_clears_stale_queue_when_capability_is_removed() -> None:
    serial_port = QueueSerial()
    hub = Esp32SerialHub(
        port="/dev/test-esp32",
        startup_timeout_s=0.5,
        serial_factory=lambda: serial_port,
    )
    hub.acquire("test")
    frames = [
        ProtocolFrame(
            MessageType.HEARTBEAT,
            1,
            100,
            struct.pack("<II", 1 << 3, 0),
        ),
        ProtocolFrame(
            MessageType.LIGHT,
            2,
            110,
            struct.pack("<f", 321.0),
        ),
        ProtocolFrame(MessageType.HEARTBEAT, 3, 120, struct.pack("<II", 0, 0)),
    ]
    serial_port.push(b"".join(encode_frame(frame) for frame in frames))
    _wait_for(lambda: hub.diagnostics()["frames_received"] == 3)

    with pytest.raises(SensorReadError, match="does not advertise"):
        hub.read_frame(MessageType.LIGHT, timeout_s=0.5)
    assert hub.diagnostics()["queue_drops"] == 1
    hub.release("test")


def test_serial_hub_reconnects_after_read_failure() -> None:
    first = QueueSerial()
    second = QueueSerial()
    first.push(OSError("USB disconnected"))
    serial_ports = deque([first, second])
    factory_lock = threading.Lock()

    def factory() -> QueueSerial:
        with factory_lock:
            if serial_ports:
                return serial_ports.popleft()
        return second

    hub = Esp32SerialHub(
        port="/dev/test-esp32",
        startup_timeout_s=0.5,
        reconnect_delay_s=0.01,
        serial_factory=factory,
    )
    hub.acquire("test")
    _wait_for(lambda: hub.diagnostics()["reconnects"] >= 1)
    light = ProtocolFrame(
        message_type=MessageType.LIGHT,
        sequence=1,
        device_uptime_ms=100,
        payload=struct.pack("<f", 321.0),
    )
    second.push(encode_frame(light))

    assert hub.read_frame(MessageType.LIGHT, timeout_s=0.5).frame == light
    assert hub.diagnostics()["reconnects"] >= 1
    hub.release("test")


def test_serial_hub_discards_stale_samples_on_disconnect() -> None:
    first = QueueSerial()
    second = QueueSerial()
    serial_ports = deque([first, second])
    factory_lock = threading.Lock()

    def factory() -> QueueSerial:
        with factory_lock:
            if serial_ports:
                return serial_ports.popleft()
        return second

    hub = Esp32SerialHub(
        port="/dev/test-esp32",
        startup_timeout_s=0.5,
        reconnect_delay_s=0.01,
        serial_factory=factory,
    )
    hub.acquire("test")
    stale = ProtocolFrame(
        message_type=MessageType.LIGHT,
        sequence=10,
        device_uptime_ms=1_000,
        payload=struct.pack("<f", 10.0),
    )
    fresh = ProtocolFrame(
        message_type=MessageType.LIGHT,
        sequence=11,
        device_uptime_ms=1_100,
        payload=struct.pack("<f", 11.0),
    )
    first.push(encode_frame(stale))
    first.push(OSError("USB disconnected"))
    _wait_for(lambda: hub.diagnostics()["reconnects"] >= 1)
    second.push(encode_frame(fresh))

    assert hub.read_frame(MessageType.LIGHT, timeout_s=0.5).frame == fresh
    assert hub.diagnostics()["queue_drops"] == 1
    hub.release("test")


def test_serial_hub_recovers_after_initial_open_failures() -> None:
    serial_port = QueueSerial()
    attempts = 0

    def factory() -> QueueSerial:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise OSError("port is not ready")
        return serial_port

    hub = Esp32SerialHub(
        port="/dev/test-esp32",
        startup_timeout_s=0.5,
        reconnect_delay_s=0.001,
        serial_factory=factory,
    )
    hub.acquire("test")

    diagnostics = hub.diagnostics()
    assert diagnostics["connected"] is True
    assert diagnostics["connection_attempts"] == 3
    assert diagnostics["last_error"] is None
    hub.release("test")


def test_serial_hub_rejects_out_of_order_and_accepts_device_reset() -> None:
    serial_port = QueueSerial()
    hub = Esp32SerialHub(
        port="/dev/test-esp32",
        startup_timeout_s=0.5,
        serial_factory=lambda: serial_port,
    )
    hub.acquire("test")
    before_reset = [
        ProtocolFrame(
            message_type=MessageType.LIGHT,
            sequence=sequence,
            device_uptime_ms=uptime_ms,
            payload=struct.pack("<f", float(sequence)),
        )
        for sequence, uptime_ms in ((10, 1_000), (12, 1_200), (11, 1_300))
    ]
    reset_heartbeat = ProtocolFrame(
        message_type=MessageType.HEARTBEAT,
        sequence=0,
        device_uptime_ms=5,
        payload=struct.pack("<II", 1 << 3, 0),
    )
    after_reset = ProtocolFrame(
        message_type=MessageType.LIGHT,
        sequence=1,
        device_uptime_ms=10,
        payload=struct.pack("<f", 99.0),
    )
    serial_port.push(
        b"".join(encode_frame(frame) for frame in before_reset)
        + encode_frame(reset_heartbeat)
        + encode_frame(after_reset)
    )
    _wait_for(lambda: hub.diagnostics()["protocol_decoded_frames"] == 5)

    received = hub.read_frame(MessageType.LIGHT, timeout_s=0.2)
    diagnostics = hub.diagnostics()
    assert received.frame == after_reset
    assert diagnostics["sequence_gaps"] == 1
    assert diagnostics["out_of_order"] == 1
    assert diagnostics["device_resets"] == 1
    assert diagnostics["queue_drops"] == 2
    hub.release("test")


def test_serial_hub_counts_invalid_semantics_and_unknown_messages() -> None:
    serial_port = QueueSerial()
    hub = Esp32SerialHub(
        port="/dev/test-esp32",
        startup_timeout_s=0.5,
        serial_factory=lambda: serial_port,
    )
    hub.acquire("test")
    frames = [
        ProtocolFrame(MessageType.HEARTBEAT, 1, 10, b"short"),
        ProtocolFrame(
            MessageType.HEALTH,
            2,
            20,
            struct.pack("<BBHI", MessageType.LIGHT, 7, 0, 0),
        ),
        ProtocolFrame(0x7F, 3, 30, b"future"),
    ]
    serial_port.push(b"".join(encode_frame(frame) for frame in frames))
    _wait_for(lambda: hub.diagnostics()["frames_received"] == 3)

    diagnostics = hub.diagnostics()
    assert diagnostics["semantic_errors"] == 2
    assert diagnostics["unknown_frames"] == 1
    assert diagnostics["capability_mask"] == 0
    hub.release("test")


def test_serial_hub_stress_keeps_only_bounded_tail() -> None:
    serial_port = QueueSerial()
    hub = Esp32SerialHub(
        port="/dev/test-esp32",
        queue_size=8,
        startup_timeout_s=0.5,
        serial_factory=lambda: serial_port,
    )
    hub.acquire("test")
    frames = [
        ProtocolFrame(
            message_type=MessageType.LIGHT,
            sequence=sequence,
            device_uptime_ms=sequence,
            payload=struct.pack("<f", float(sequence)),
        )
        for sequence in range(1, 1_001)
    ]
    serial_port.push(b"".join(encode_frame(frame) for frame in frames))
    _wait_for(
        lambda: hub.diagnostics()["protocol_decoded_frames"] == 1_000,
        timeout_s=2.0,
    )

    received = [
        hub.read_frame(MessageType.LIGHT, timeout_s=0.2).frame.sequence
        for _ in range(8)
    ]
    diagnostics = hub.diagnostics()
    assert received == list(range(993, 1_001))
    assert diagnostics["queue_drops"] == 992
    assert diagnostics["queue_depths"][str(int(MessageType.LIGHT))] == 0
    hub.release("test")


def test_hub_adapters_emit_unchanged_complete_window() -> None:
    serial_port = QueueSerial()
    clock = ManualClock(start=NOW)
    hub = Esp32SerialHub(
        port="/dev/test-esp32",
        startup_timeout_s=0.5,
        serial_factory=lambda: serial_port,
        clock=clock,
    )
    common = {
        "hub": hub,
        "sample_timeout_s": 0.2,
        "sample_rate_hz": 0.2,
        "max_retries": 0,
        "clock": clock,
    }
    drivers = {
        "thermal": Esp32HubThermalDriver(**common),
        "radar": Esp32HubRadarDriver(**common),
        "sound": Esp32HubSoundDriver(**common),
        "light": Esp32HubLightDriver(**common),
        "climate": Esp32HubClimateDriver(**common),
    }
    orchestrator = SensorOrchestrator(
        room_id="room_a",
        device_id="pi5-a",
        window_seconds=5,
        drivers=drivers,
        clock=clock,
    )
    frames = [
        ProtocolFrame(
            MessageType.HEARTBEAT,
            1,
            100,
            struct.pack("<II", 0x1F, 0),
        ),
        ProtocolFrame(MessageType.THERMAL, 2, 110, _thermal_payload()),
        ProtocolFrame(MessageType.RADAR, 3, 120, _radar_payload()),
        ProtocolFrame(
            MessageType.SOUND,
            4,
            130,
            struct.pack("<fffH", 0.2, 0.05, 0.4, 400),
        ),
        ProtocolFrame(MessageType.LIGHT, 5, 140, _light_payload()),
        ProtocolFrame(
            MessageType.CLIMATE,
            6,
            150,
            struct.pack("<ff", 24.5, 61.0),
        ),
    ]
    try:
        orchestrator.start()
        serial_port.push(b"".join(encode_frame(frame) for frame in frames))
        _wait_for(lambda: hub.diagnostics()["frames_received"] == 6)
        window = orchestrator.run_window()
    finally:
        orchestrator.close()

    assert window.payload["schema_version"] == "1.0"
    assert window.payload["thermal"]["frame_count"] == 1
    assert window.payload["radar"]["sample_count"] == 1
    assert window.payload["sound"]["rms_mean"] == pytest.approx(0.2)
    assert window.payload["environment"] == {
        "light_lux": None,
        "temperature_c": pytest.approx(24.5),
        "humidity_pct": pytest.approx(61.0),
    }
    assert window.payload["quality"] == {
        "completeness": 1.0,
        "warnings": ["hw486_uncalibrated_light_proxy"],
    }
    assert len(window.thermal_frames) == 1
    assert "raw_audio" not in str(window.payload).lower()


def test_bootstrap_builds_five_adapters_sharing_one_hub() -> None:
    config = config_from_dict(
        {
            "room_id": "room_a",
            "device_id": "pi5-a",
            "simulator": {"enabled": False},
            "transport": {
                "mode": "esp32_hub",
                "port": "/dev/serial/by-id/esp32-test",
            },
        }
    )
    drivers = build_real_drivers(config, ManualClock())

    assert set(drivers) == {"thermal", "radar", "sound", "light", "climate"}
    hubs = {id(driver.hub) for driver in drivers.values()}  # type: ignore[attr-defined]
    assert len(hubs) == 1
    assert isinstance(drivers["thermal"], Esp32HubThermalDriver)
    assert isinstance(drivers["radar"], Esp32HubRadarDriver)


def test_shared_hub_close_is_idempotent() -> None:
    serial_port = QueueSerial()
    hub = Esp32SerialHub(
        port="/dev/test-esp32",
        startup_timeout_s=0.5,
        serial_factory=lambda: serial_port,
    )
    hub.acquire("thermal")
    hub.acquire("radar")
    hub.release("thermal")
    assert hub.diagnostics()["connected"] is True
    hub.release("radar")
    hub.close()
    hub.close()
    assert hub.diagnostics()["connected"] is False
