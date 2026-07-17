"""HLK-LD2450 report framing and serial driver.

The byte-field layout is adapted from the MIT-licensed csRon/HLK-LD2450
reference at commit 1b65a026873ab2db3d22d3b3bb99ef16fbcdd4f0 and checked
against the vendor serial-protocol document included with that repository.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .base import BaseSensorDriver, SensorReadError, SensorStartError
from ..clock import Clock
from ..models import RadarTarget, SampleQuality, SensorSample


REPORT_HEADER = bytes.fromhex("AA FF 03 00")
REPORT_TAIL = bytes.fromhex("55 CC")
REPORT_LENGTH = 30
TARGET_LENGTH = 8
TARGET_COUNT = 3


def decode_signed_magnitude_15(raw: int) -> int:
    """Decode LD2450's bit-15 sign plus 15-bit magnitude representation."""

    magnitude = raw & 0x7FFF
    return -magnitude if raw & 0x8000 else magnitude


def parse_report_frame(frame: bytes) -> tuple[RadarTarget, ...]:
    if len(frame) != REPORT_LENGTH:
        raise ValueError(f"LD2450 report must be {REPORT_LENGTH} bytes")
    if not frame.startswith(REPORT_HEADER) or not frame.endswith(REPORT_TAIL):
        raise ValueError("LD2450 report has an invalid header or tail")

    targets: list[RadarTarget] = []
    for slot in range(TARGET_COUNT):
        start = len(REPORT_HEADER) + slot * TARGET_LENGTH
        block = frame[start : start + TARGET_LENGTH]
        raw_x = int.from_bytes(block[0:2], "little", signed=False)
        raw_y = int.from_bytes(block[2:4], "little", signed=False)
        raw_speed = int.from_bytes(block[4:6], "little", signed=False)
        resolution = int.from_bytes(block[6:8], "little", signed=False)
        valid = any((raw_x, raw_y, raw_speed, resolution))
        targets.append(
            RadarTarget(
                slot=slot,
                x_mm=decode_signed_magnitude_15(raw_x),
                y_mm=decode_signed_magnitude_15(raw_y),
                speed_cm_s=decode_signed_magnitude_15(raw_speed),
                distance_resolution_mm=resolution,
                valid=valid,
            )
        )
    return tuple(targets)


class RadarFrameStream:
    """Incremental report extractor that survives noise and partial reads."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self.invalid_chunks = 0

    @property
    def buffered_bytes(self) -> int:
        """Bytes retained while waiting for a possible frame boundary."""

        return len(self._buffer)

    def feed(self, chunk: bytes) -> list[bytes]:
        if chunk:
            self._buffer.extend(chunk)
        frames: list[bytes] = []
        while True:
            header_at = self._buffer.find(REPORT_HEADER)
            if header_at < 0:
                if len(self._buffer) > len(REPORT_HEADER) - 1:
                    del self._buffer[: -(len(REPORT_HEADER) - 1)]
                    self.invalid_chunks += 1
                break
            if header_at:
                del self._buffer[:header_at]
                self.invalid_chunks += 1
            if len(self._buffer) < REPORT_LENGTH:
                break
            candidate = bytes(self._buffer[:REPORT_LENGTH])
            if not candidate.endswith(REPORT_TAIL):
                del self._buffer[0]
                self.invalid_chunks += 1
                continue
            frames.append(candidate)
            del self._buffer[:REPORT_LENGTH]
        return frames


class LD2450Driver(BaseSensorDriver):
    def __init__(
        self,
        *,
        port: str = "/dev/ttyUSB0",
        baud_rate: int = 256_000,
        timeout_s: float = 0.25,
        sample_rate_hz: float = 10.0,
        serial_factory: Callable[[], Any] | None = None,
        max_retries: int = 1,
        offline_threshold: int = 3,
        clock: Clock | None = None,
    ) -> None:
        super().__init__(
            "radar",
            sample_rate_hz=sample_rate_hz,
            max_retries=max_retries,
            offline_threshold=offline_threshold,
            clock=clock,
        )
        self.port = port
        self.baud_rate = int(baud_rate)
        self.timeout_s = float(timeout_s)
        self._serial_factory = serial_factory
        self._serial: Any = None
        self._stream = RadarFrameStream()
        self.valid_frames = 0

    def _start(self) -> None:
        if self._serial_factory is not None:
            self._serial = self._serial_factory()
            return
        try:
            import serial
        except ImportError as exc:
            raise SensorStartError(
                "pyserial is required for the LD2450 driver"
            ) from exc
        self._serial = serial.Serial(
            self.port,
            self.baud_rate,
            timeout=self.timeout_s,
        )

    def _read(self) -> SensorSample:
        deadline = self.clock.monotonic() + self.timeout_s
        while self.clock.monotonic() <= deadline:
            chunk = self._serial.read(64)
            frames = self._stream.feed(bytes(chunk))
            if frames:
                targets = parse_report_frame(frames[-1])
                self.valid_frames += 1
                self._tracker.details.update(
                    {
                        "valid_frames": self.valid_frames,
                        "invalid_chunks": self._stream.invalid_chunks,
                        "buffered_bytes": self._stream.buffered_bytes,
                        "active_targets": sum(target.valid for target in targets),
                    }
                )
                return SensorSample(
                    sensor=self.name,
                    captured_at=self.clock.now_utc(),
                    monotonic_s=self.clock.monotonic(),
                    values={"targets": targets},
                    units={
                        "x_mm": "millimetres",
                        "y_mm": "millimetres",
                        "speed_cm_s": "centimetres_per_second",
                        "distance_resolution_mm": "millimetres",
                    },
                    quality=SampleQuality.VALID,
                    source="hlk-ld2450",
                )
            self.clock.sleep(0.001)
        self._tracker.details["invalid_chunks"] = self._stream.invalid_chunks
        self._tracker.details["buffered_bytes"] = self._stream.buffered_bytes
        raise SensorReadError("timed out waiting for a complete LD2450 report")

    def _close(self) -> None:
        if self._serial is not None and hasattr(self._serial, "close"):
            self._serial.close()
        self._serial = None
