"""ESP32 sensor-hub transport and SensorDriver-compatible adapters."""

from __future__ import annotations

import math
import struct
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .base import (
    BaseSensorDriver,
    SensorReadError,
    SensorStartError,
    SensorValidationError,
)
from .ld2450 import REPORT_LENGTH, parse_report_frame
from ..clock import Clock, SystemClock
from ..esp32_protocol import (
    SENSOR_MESSAGE_TYPES,
    Esp32FrameStream,
    MessageType,
    ProtocolFrame,
)
from ..models import (
    SampleQuality,
    SensorSample,
    THERMAL_HEIGHT,
    THERMAL_PIXELS,
    THERMAL_WIDTH,
)


_HEARTBEAT_PAYLOAD = struct.Struct("<II")
_HEALTH_PAYLOAD = struct.Struct("<BBHI")
_SOUND_PAYLOAD = struct.Struct("<fffH")
_LIGHT_PAYLOAD = struct.Struct("<HffB")
_CLIMATE_PAYLOAD = struct.Struct("<ff")
_LIGHT_FLAG_CALIBRATED_LUX = 1 << 0
_LIGHT_KNOWN_FLAGS = _LIGHT_FLAG_CALIBRATED_LUX

_CAPABILITY_BITS = {
    int(MessageType.THERMAL): 1 << 0,
    int(MessageType.RADAR): 1 << 1,
    int(MessageType.SOUND): 1 << 2,
    int(MessageType.LIGHT): 1 << 3,
    int(MessageType.CLIMATE): 1 << 4,
}


@dataclass(frozen=True, slots=True)
class ReceivedHubFrame:
    frame: ProtocolFrame
    received_at: datetime
    received_monotonic_s: float


class Esp32SerialHub:
    """Own one serial connection and demultiplex validated sensor packets.

    Multiple sensor adapters share this object.  A background reader is active
    while at least one adapter is acquired.  It reconnects after serial errors,
    bounds every per-sensor queue, and never logs sensor payloads.
    """

    def __init__(
        self,
        *,
        port: str,
        baud_rate: int = 460_800,
        read_timeout_s: float = 0.05,
        reconnect_delay_s: float = 0.25,
        startup_timeout_s: float = 2.0,
        queue_size: int = 64,
        serial_factory: Callable[[], Any] | None = None,
        clock: Clock | None = None,
    ) -> None:
        if not port:
            raise ValueError("ESP32 hub port cannot be empty")
        if baud_rate <= 0:
            raise ValueError("ESP32 hub baud_rate must be positive")
        if read_timeout_s <= 0:
            raise ValueError("ESP32 hub read_timeout_s must be positive")
        if reconnect_delay_s < 0:
            raise ValueError("ESP32 hub reconnect_delay_s cannot be negative")
        if startup_timeout_s <= 0:
            raise ValueError("ESP32 hub startup_timeout_s must be positive")
        if queue_size < 1:
            raise ValueError("ESP32 hub queue_size must be at least 1")

        self.port = port
        self.baud_rate = int(baud_rate)
        self.read_timeout_s = float(read_timeout_s)
        self.reconnect_delay_s = float(reconnect_delay_s)
        self.startup_timeout_s = float(startup_timeout_s)
        self.queue_size = int(queue_size)
        self._serial_factory = serial_factory
        self.clock = clock or SystemClock()

        self._condition = threading.Condition()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._serial: Any = None
        self._connected = False
        self._clients: set[str] = set()
        self._stream = Esp32FrameStream()
        self._queues: dict[int, deque[ReceivedHubFrame]] = {
            int(message_type): deque()
            for message_type in SENSOR_MESSAGE_TYPES
        }
        self._queue_drops: defaultdict[int, int] = defaultdict(int)
        self._remote_health: dict[int, tuple[int, int, int]] = {}

        self._connection_attempts = 0
        self._successful_connections = 0
        self._reconnects = 0
        self._bytes_read = 0
        self._frames_received = 0
        self._semantic_errors = 0
        self._unknown_frames = 0
        self._sequence_gaps = 0
        self._duplicates = 0
        self._out_of_order = 0
        self._device_resets = 0
        self._last_sequence: int | None = None
        self._last_uptime_ms: int | None = None
        self._heartbeat_seen = False
        self._capability_mask = 0
        self._device_dropped_samples = 0
        self._last_error: str | None = None

    def acquire(self, client: str) -> None:
        """Start or share the reader and wait for the serial port to open."""

        should_stop = False
        error: str | None = None
        with self._condition:
            self._clients.add(client)
            self._ensure_reader_locked()
            deadline = time.monotonic() + self.startup_timeout_s
            while not self._connected:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._clients.discard(client)
                    should_stop = not self._clients
                    error = self._last_error or "connection timed out"
                    break
                self._condition.wait(timeout=remaining)

        if should_stop:
            self._shutdown_reader()
        if error is not None:
            raise SensorStartError(f"ESP32 hub failed to connect: {error}")

    def release(self, client: str) -> None:
        """Release one adapter and stop the reader after the last release."""

        with self._condition:
            self._clients.discard(client)
            should_stop = not self._clients
        if should_stop:
            self._shutdown_reader()

    def close(self) -> None:
        """Force all clients and the serial reader to close."""

        with self._condition:
            self._clients.clear()
        self._shutdown_reader()

    def read_frame(
        self,
        message_type: int | MessageType,
        *,
        timeout_s: float,
    ) -> ReceivedHubFrame:
        """Return the oldest queued frame for one sensor message type."""

        numeric_type = int(message_type)
        if numeric_type not in self._queues:
            raise ValueError(f"message type {numeric_type} is not a sensor queue")
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")

        with self._condition:
            deadline = time.monotonic() + timeout_s
            while True:
                queue = self._queues[numeric_type]
                if queue:
                    return queue.popleft()
                if self._heartbeat_seen:
                    capability = _CAPABILITY_BITS[numeric_type]
                    if not self._capability_mask & capability:
                        raise SensorReadError(
                            "ESP32 hub does not advertise this sensor"
                        )
                remote_health = self._remote_health.get(numeric_type)
                if remote_health is not None and remote_health[0] == 2:
                    raise SensorReadError(
                        "ESP32 hub reports this sensor offline"
                    )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    detail = f": {self._last_error}" if self._last_error else ""
                    raise SensorReadError(
                        f"timed out waiting for ESP32 hub sample{detail}"
                    )
                self._condition.wait(timeout=remaining)

    def diagnostics(self) -> dict[str, Any]:
        """Return payload-free transport counters for health reporting."""

        with self._condition:
            protocol = self._stream.stats()
            return {
                "connected": self._connected,
                "connection_attempts": self._connection_attempts,
                "reconnects": self._reconnects,
                "bytes_read": self._bytes_read,
                "frames_received": self._frames_received,
                "semantic_errors": self._semantic_errors,
                "unknown_frames": self._unknown_frames,
                "sequence_gaps": self._sequence_gaps,
                "duplicates": self._duplicates,
                "out_of_order": self._out_of_order,
                "device_resets": self._device_resets,
                "queue_drops": sum(self._queue_drops.values()),
                "device_dropped_samples": self._device_dropped_samples,
                "capability_mask": self._capability_mask,
                "last_error": self._last_error,
                "protocol_decoded_frames": protocol.decoded_frames,
                "protocol_invalid_frames": protocol.invalid_frames,
                "protocol_checksum_errors": protocol.checksum_errors,
                "protocol_version_errors": protocol.version_errors,
                "protocol_oversize_frames": protocol.oversize_frames,
                "protocol_buffered_bytes": protocol.buffered_bytes,
                "queue_depths": {
                    str(message_type): len(queue)
                    for message_type, queue in self._queues.items()
                },
            }

    def _ensure_reader_locked(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._reader_loop,
            name="esp32-sensor-hub-reader",
            daemon=True,
        )
        self._thread.start()

    def _open_serial(self) -> Any:
        if self._serial_factory is not None:
            return self._serial_factory()
        try:
            import serial
        except ImportError as exc:
            raise SensorStartError(
                "pyserial is required for ESP32 hub mode"
            ) from exc
        return serial.Serial(
            self.port,
            self.baud_rate,
            timeout=self.read_timeout_s,
        )

    def _reader_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._condition:
                self._connection_attempts += 1
            try:
                serial_port = self._open_serial()
            except Exception as exc:
                self._record_disconnect(exc)
                self._stop_event.wait(self.reconnect_delay_s)
                continue

            with self._condition:
                self._serial = serial_port
                self._connected = True
                self._last_error = None
                self._successful_connections += 1
                if self._successful_connections > 1:
                    self._reconnects += 1
                self._condition.notify_all()

            try:
                while not self._stop_event.is_set():
                    chunk = bytes(serial_port.read(512))
                    if not chunk:
                        continue
                    received_at = self.clock.now_utc()
                    received_monotonic_s = self.clock.monotonic()
                    with self._condition:
                        self._bytes_read += len(chunk)
                        self._ingest_locked(
                            chunk,
                            received_at=received_at,
                            received_monotonic_s=received_monotonic_s,
                        )
                        self._condition.notify_all()
            except Exception as exc:
                if not self._stop_event.is_set():
                    self._record_disconnect(exc)
            finally:
                try:
                    serial_port.close()
                except Exception:
                    pass
                with self._condition:
                    if self._serial is serial_port:
                        self._serial = None
                    self._connected = False
                    self._stream.reset_partial()
                    self._condition.notify_all()

            if not self._stop_event.is_set():
                self._stop_event.wait(self.reconnect_delay_s)

    def _record_disconnect(self, exc: Exception) -> None:
        with self._condition:
            self._connected = False
            self._invalidate_remote_state_locked()
            self._last_error = f"{type(exc).__name__}: {exc}"
            self._condition.notify_all()

    def _invalidate_remote_state_locked(self) -> None:
        """Discard samples and availability learned from an old connection."""

        for message_type, queue in self._queues.items():
            self._queue_drops[message_type] += len(queue)
            queue.clear()
        self._heartbeat_seen = False
        self._capability_mask = 0
        self._device_dropped_samples = 0
        self._remote_health.clear()

    def _ingest_locked(
        self,
        chunk: bytes,
        *,
        received_at: datetime,
        received_monotonic_s: float,
    ) -> None:
        for frame in self._stream.feed(chunk):
            if not self._accept_sequence_locked(frame):
                continue
            self._frames_received += 1
            if frame.message_type == MessageType.HEARTBEAT:
                self._handle_heartbeat_locked(frame.payload)
                continue
            if frame.message_type == MessageType.HEALTH:
                self._handle_health_locked(frame.payload)
                continue
            if frame.message_type not in self._queues:
                self._unknown_frames += 1
                continue

            queue = self._queues[frame.message_type]
            if len(queue) >= self.queue_size:
                queue.popleft()
                self._queue_drops[frame.message_type] += 1
            queue.append(
                ReceivedHubFrame(
                    frame=frame,
                    received_at=received_at,
                    received_monotonic_s=received_monotonic_s,
                )
            )

    def _accept_sequence_locked(self, frame: ProtocolFrame) -> bool:
        if self._last_sequence is None:
            self._last_sequence = frame.sequence
            self._last_uptime_ms = frame.device_uptime_ms
            return True

        expected = (self._last_sequence + 1) & 0xFFFFFFFF
        if frame.sequence == expected:
            self._last_sequence = frame.sequence
            self._last_uptime_ms = frame.device_uptime_ms
            return True
        if frame.sequence == self._last_sequence:
            self._duplicates += 1
            return False
        if (
            self._last_uptime_ms is not None
            and frame.device_uptime_ms < self._last_uptime_ms
            and frame.sequence < self._last_sequence
        ):
            self._device_resets += 1
            self._invalidate_remote_state_locked()
            self._last_sequence = frame.sequence
            self._last_uptime_ms = frame.device_uptime_ms
            return True

        forward_gap = (frame.sequence - expected) & 0xFFFFFFFF
        if forward_gap < 0x80000000:
            self._sequence_gaps += forward_gap
            self._last_sequence = frame.sequence
            self._last_uptime_ms = frame.device_uptime_ms
            return True

        self._out_of_order += 1
        return False

    def _handle_heartbeat_locked(self, payload: bytes) -> None:
        if len(payload) != _HEARTBEAT_PAYLOAD.size:
            self._semantic_errors += 1
            return
        capability_mask, self._device_dropped_samples = (
            _HEARTBEAT_PAYLOAD.unpack(payload)
        )
        removed_capabilities = self._capability_mask & ~capability_mask
        for message_type, capability in _CAPABILITY_BITS.items():
            if removed_capabilities & capability:
                queue = self._queues[message_type]
                self._queue_drops[message_type] += len(queue)
                queue.clear()
        self._capability_mask = capability_mask
        self._heartbeat_seen = True

    def _handle_health_locked(self, payload: bytes) -> None:
        if len(payload) != _HEALTH_PAYLOAD.size:
            self._semantic_errors += 1
            return
        sensor_type, status, error_code, event_count = _HEALTH_PAYLOAD.unpack(
            payload
        )
        if sensor_type not in self._queues or status > 2:
            self._semantic_errors += 1
            return
        self._remote_health[sensor_type] = (status, error_code, event_count)
        if status == 2:
            queue = self._queues[sensor_type]
            self._queue_drops[sensor_type] += len(queue)
            queue.clear()

    def _shutdown_reader(self) -> None:
        self._stop_event.set()
        with self._condition:
            serial_port = self._serial
            thread = self._thread
            self._condition.notify_all()
        if serial_port is not None:
            try:
                serial_port.close()
            except Exception:
                pass
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(1.0, self.read_timeout_s * 4))
        with self._condition:
            self._thread = None
            self._serial = None
            self._connected = False
            self._invalidate_remote_state_locked()
            self._condition.notify_all()


class Esp32HubSensorDriver(BaseSensorDriver):
    """Common lifecycle for one logical sensor carried by the shared hub."""

    message_type: MessageType

    def __init__(
        self,
        name: str,
        *,
        hub: Esp32SerialHub,
        sample_timeout_s: float,
        sample_rate_hz: float,
        max_retries: int,
        offline_threshold: int,
        clock: Clock | None,
    ) -> None:
        super().__init__(
            name,
            sample_rate_hz=sample_rate_hz,
            max_retries=max_retries,
            offline_threshold=offline_threshold,
            clock=clock,
        )
        if sample_timeout_s <= 0:
            raise ValueError("sample_timeout_s must be positive")
        self.hub = hub
        self.sample_timeout_s = float(sample_timeout_s)

    def _start(self) -> None:
        self.hub.acquire(self.name)

    def _receive(self) -> ReceivedHubFrame:
        received = self.hub.read_frame(
            self.message_type,
            timeout_s=self.sample_timeout_s,
        )
        diagnostics = self.hub.diagnostics()
        self._tracker.details.update(
            {
                "transport": "esp32_hub",
                "hub_sequence_gaps": diagnostics["sequence_gaps"],
                "hub_queue_drops": diagnostics["queue_drops"],
                "hub_reconnects": diagnostics["reconnects"],
                "hub_protocol_invalid_frames": diagnostics[
                    "protocol_invalid_frames"
                ],
                "last_hub_sequence": received.frame.sequence,
                "last_device_uptime_ms": received.frame.device_uptime_ms,
            }
        )
        return received

    def _close(self) -> None:
        self.hub.release(self.name)


class Esp32HubThermalDriver(Esp32HubSensorDriver):
    message_type = MessageType.THERMAL

    def __init__(
        self,
        *,
        hub: Esp32SerialHub,
        sample_timeout_s: float = 0.75,
        sample_rate_hz: float = 2.0,
        minimum_c: float = -40.0,
        maximum_c: float = 300.0,
        max_retries: int = 2,
        offline_threshold: int = 3,
        clock: Clock | None = None,
    ) -> None:
        super().__init__(
            "thermal",
            hub=hub,
            sample_timeout_s=sample_timeout_s,
            sample_rate_hz=sample_rate_hz,
            max_retries=max_retries,
            offline_threshold=offline_threshold,
            clock=clock,
        )
        if minimum_c >= maximum_c:
            raise ValueError("minimum_c must be lower than maximum_c")
        self.minimum_c = float(minimum_c)
        self.maximum_c = float(maximum_c)

    def _read(self) -> SensorSample:
        received = self._receive()
        payload = received.frame.payload
        if len(payload) < 2:
            raise SensorValidationError("thermal payload is shorter than dimensions")
        width, height = payload[0], payload[1]
        if (width, height) != (THERMAL_WIDTH, THERMAL_HEIGHT):
            raise SensorValidationError(
                f"expected {THERMAL_WIDTH}x{THERMAL_HEIGHT} thermal frame, "
                f"got {width}x{height}"
            )
        expected_size = 2 + THERMAL_PIXELS * 2
        if len(payload) != expected_size:
            raise SensorValidationError(
                f"expected {expected_size} thermal payload bytes, got {len(payload)}"
            )
        raw_temperatures = struct.unpack_from(
            f"<{THERMAL_PIXELS}h",
            payload,
            2,
        )
        temperatures = tuple(value / 100.0 for value in raw_temperatures)
        invalid = [
            value
            for value in temperatures
            if not self.minimum_c <= value <= self.maximum_c
        ]
        if invalid:
            raise SensorValidationError(
                f"thermal frame contains {len(invalid)} invalid pixel(s)"
            )
        return SensorSample(
            sensor=self.name,
            captured_at=received.received_at,
            monotonic_s=received.received_monotonic_s,
            values={
                "width": width,
                "height": height,
                "temperatures_c": temperatures,
            },
            units={"temperatures_c": "celsius"},
            quality=SampleQuality.VALID,
            source="esp32-hub:mlx90640",
        )


class Esp32HubRadarDriver(Esp32HubSensorDriver):
    message_type = MessageType.RADAR

    def __init__(
        self,
        *,
        hub: Esp32SerialHub,
        sample_timeout_s: float = 0.75,
        sample_rate_hz: float = 10.0,
        max_retries: int = 1,
        offline_threshold: int = 3,
        clock: Clock | None = None,
    ) -> None:
        super().__init__(
            "radar",
            hub=hub,
            sample_timeout_s=sample_timeout_s,
            sample_rate_hz=sample_rate_hz,
            max_retries=max_retries,
            offline_threshold=offline_threshold,
            clock=clock,
        )

    def _read(self) -> SensorSample:
        received = self._receive()
        payload = received.frame.payload
        if len(payload) != REPORT_LENGTH:
            raise SensorValidationError(
                f"expected {REPORT_LENGTH} radar bytes, got {len(payload)}"
            )
        try:
            targets = parse_report_frame(payload)
        except ValueError as exc:
            raise SensorValidationError(str(exc)) from exc
        return SensorSample(
            sensor=self.name,
            captured_at=received.received_at,
            monotonic_s=received.received_monotonic_s,
            values={"targets": targets},
            units={
                "x_mm": "millimetres",
                "y_mm": "millimetres",
                "speed_cm_s": "centimetres_per_second",
                "distance_resolution_mm": "millimetres",
            },
            quality=SampleQuality.VALID,
            source="esp32-hub:hlk-ld2450",
        )


class Esp32HubSoundDriver(Esp32HubSensorDriver):
    message_type = MessageType.SOUND

    def __init__(
        self,
        *,
        hub: Esp32SerialHub,
        sample_timeout_s: float = 0.75,
        sample_rate_hz: float = 4.0,
        max_retries: int = 1,
        offline_threshold: int = 3,
        clock: Clock | None = None,
    ) -> None:
        super().__init__(
            "sound",
            hub=hub,
            sample_timeout_s=sample_timeout_s,
            sample_rate_hz=sample_rate_hz,
            max_retries=max_retries,
            offline_threshold=offline_threshold,
            clock=clock,
        )
        self.raw_audio_persisted = False

    def _read(self) -> SensorSample:
        received = self._receive()
        payload = received.frame.payload
        if len(payload) != _SOUND_PAYLOAD.size:
            raise SensorValidationError(
                f"expected {_SOUND_PAYLOAD.size} sound bytes, got {len(payload)}"
            )
        rms, std, peak, chunk_frames = _SOUND_PAYLOAD.unpack(payload)
        values = (rms, std, peak)
        if not all(math.isfinite(value) and 0 <= value <= 1 for value in values):
            raise SensorValidationError(
                "sound statistics must be finite normalized values"
            )
        if chunk_frames < 1:
            raise SensorValidationError("sound chunk_frames must be positive")
        return SensorSample(
            sensor=self.name,
            captured_at=received.received_at,
            monotonic_s=received.received_monotonic_s,
            values={
                "rms": float(rms),
                "std": float(std),
                "peak": float(peak),
                "raw_audio_persisted": False,
                "chunk_frames": chunk_frames,
            },
            units={"rms": "normalized", "std": "normalized", "peak": "normalized"},
            quality=SampleQuality.VALID,
            source="esp32-hub:hw485-relative-sound",
        )


class Esp32HubLightDriver(Esp32HubSensorDriver):
    message_type = MessageType.LIGHT

    def __init__(
        self,
        *,
        hub: Esp32SerialHub,
        sample_timeout_s: float = 0.75,
        sample_rate_hz: float = 1.0,
        max_retries: int = 1,
        offline_threshold: int = 3,
        clock: Clock | None = None,
    ) -> None:
        super().__init__(
            "light",
            hub=hub,
            sample_timeout_s=sample_timeout_s,
            sample_rate_hz=sample_rate_hz,
            max_retries=max_retries,
            offline_threshold=offline_threshold,
            clock=clock,
        )

    def _read(self) -> SensorSample:
        received = self._receive()
        payload = received.frame.payload
        if len(payload) != _LIGHT_PAYLOAD.size:
            raise SensorValidationError(
                f"expected {_LIGHT_PAYLOAD.size} light bytes, got {len(payload)}"
            )
        adc_raw, normalized, calibrated_lux, flags = _LIGHT_PAYLOAD.unpack(
            payload
        )
        if adc_raw > 4095:
            raise SensorValidationError(f"invalid HW-486 ADC value: {adc_raw}")
        if not math.isfinite(normalized) or not 0 <= normalized <= 1:
            raise SensorValidationError(
                f"invalid HW-486 normalized value: {normalized}"
            )
        if flags & ~_LIGHT_KNOWN_FLAGS:
            raise SensorValidationError(f"unknown HW-486 light flags: {flags}")
        is_calibrated = bool(flags & _LIGHT_FLAG_CALIBRATED_LUX)
        if is_calibrated and (
            not math.isfinite(calibrated_lux) or calibrated_lux < 0
        ):
            raise SensorValidationError(
                f"invalid calibrated light level: {calibrated_lux}"
            )
        light_lux = float(calibrated_lux) if is_calibrated else None
        values: dict[str, Any] = {
            "light_adc_raw": adc_raw,
            "light_normalized": float(normalized),
            "light_lux": light_lux,
            "measurement_source": "hw486_ldr_proxy",
            "calibrated_lux": is_calibrated,
        }
        if not is_calibrated:
            values["warning"] = "hw486_uncalibrated_light_proxy"
        return SensorSample(
            sensor=self.name,
            captured_at=received.received_at,
            monotonic_s=received.received_monotonic_s,
            values=values,
            units={
                "light_adc_raw": "adc_count",
                "light_normalized": "relative",
                "light_lux": "lux",
            },
            quality=SampleQuality.VALID,
            source="esp32-hub:hw486-ldr-proxy",
        )


class Esp32HubClimateDriver(Esp32HubSensorDriver):
    message_type = MessageType.CLIMATE

    def __init__(
        self,
        *,
        hub: Esp32SerialHub,
        sample_timeout_s: float = 0.75,
        sample_rate_hz: float = 1.0,
        max_retries: int = 1,
        offline_threshold: int = 3,
        clock: Clock | None = None,
    ) -> None:
        super().__init__(
            "climate",
            hub=hub,
            sample_timeout_s=sample_timeout_s,
            sample_rate_hz=sample_rate_hz,
            max_retries=max_retries,
            offline_threshold=offline_threshold,
            clock=clock,
        )

    def _read(self) -> SensorSample:
        received = self._receive()
        payload = received.frame.payload
        if len(payload) != _CLIMATE_PAYLOAD.size:
            raise SensorValidationError(
                f"expected {_CLIMATE_PAYLOAD.size} climate bytes, got {len(payload)}"
            )
        temperature_c, humidity_pct = _CLIMATE_PAYLOAD.unpack(payload)
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
            captured_at=received.received_at,
            monotonic_s=received.received_monotonic_s,
            values={
                "temperature_c": float(temperature_c),
                "humidity_pct": float(humidity_pct),
                "measurement_source": "dht11",
            },
            units={
                "temperature_c": "celsius",
                "humidity_pct": "percent_relative_humidity",
            },
            quality=SampleQuality.VALID,
            source="esp32-hub:dht11",
        )
