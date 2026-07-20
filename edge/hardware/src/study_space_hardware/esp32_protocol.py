"""Versioned binary framing for the ESP32 sensor hub serial link.

The wire format is deliberately independent of the shared Module 1 window
contract.  It transports local sensor samples from the ESP32 to the Raspberry
Pi, where the samples are converted back into the existing ``SensorDriver``
interface.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from enum import IntEnum


MAGIC = b"PSSA"
PROTOCOL_VERSION = 1
FRAME_DELIMITER = 0
MAX_PAYLOAD_BYTES = 2_048

_HEADER = struct.Struct("<4sBBIIH")
_CRC = struct.Struct("<I")
MIN_DECODED_FRAME_BYTES = _HEADER.size + _CRC.size
MAX_DECODED_FRAME_BYTES = MIN_DECODED_FRAME_BYTES + MAX_PAYLOAD_BYTES
# COBS adds at most one code byte for every 254 input bytes, plus the first
# code byte.  Keep a small explicit margin while still bounding garbage input.
MAX_ENCODED_FRAME_BYTES = (
    MAX_DECODED_FRAME_BYTES + (MAX_DECODED_FRAME_BYTES // 254) + 2
)


class MessageType(IntEnum):
    """Stable message identifiers shared with the ESP32 firmware."""

    HEARTBEAT = 0x01
    HEALTH = 0x02
    THERMAL = 0x10
    RADAR = 0x11
    SOUND = 0x12
    LIGHT = 0x13
    CLIMATE = 0x14


SENSOR_MESSAGE_TYPES = frozenset(
    {
        MessageType.THERMAL,
        MessageType.RADAR,
        MessageType.SOUND,
        MessageType.LIGHT,
        MessageType.CLIMATE,
    }
)


class ProtocolError(ValueError):
    """Base class for malformed or unsupported serial frames."""


class FramingError(ProtocolError):
    """COBS framing is malformed."""


class PacketValidationError(ProtocolError):
    """A decoded packet violates the protocol contract."""


class UnsupportedVersionError(PacketValidationError):
    """A packet uses a protocol version this host cannot decode."""


class ChecksumError(PacketValidationError):
    """A packet CRC32 does not match its contents."""


@dataclass(frozen=True, slots=True)
class ProtocolFrame:
    """One validated ESP32 hub packet after COBS decoding."""

    message_type: int
    sequence: int
    device_uptime_ms: int
    payload: bytes
    version: int = PROTOCOL_VERSION


@dataclass(frozen=True, slots=True)
class FrameStreamStats:
    decoded_frames: int
    invalid_frames: int
    checksum_errors: int
    version_errors: int
    oversize_frames: int
    buffered_bytes: int


def cobs_encode(data: bytes) -> bytes:
    """Encode bytes with Consistent Overhead Byte Stuffing (COBS)."""

    encoded = bytearray([0])
    code_index = 0
    code = 1
    for value in data:
        if value == 0:
            encoded[code_index] = code
            code_index = len(encoded)
            encoded.append(0)
            code = 1
            continue

        encoded.append(value)
        code += 1
        if code == 0xFF:
            encoded[code_index] = code
            code_index = len(encoded)
            encoded.append(0)
            code = 1

    encoded[code_index] = code
    return bytes(encoded)


def cobs_decode(encoded: bytes) -> bytes:
    """Decode one COBS payload without its trailing zero delimiter."""

    if not encoded:
        raise FramingError("COBS frame is empty")
    if FRAME_DELIMITER in encoded:
        raise FramingError("COBS frame contains an unexpected zero byte")

    decoded = bytearray()
    index = 0
    while index < len(encoded):
        code = encoded[index]
        index += 1
        block_end = index + code - 1
        if block_end > len(encoded):
            raise FramingError("COBS code extends beyond the frame")
        decoded.extend(encoded[index:block_end])
        index = block_end
        if code != 0xFF and index < len(encoded):
            decoded.append(0)
    return bytes(decoded)


def encode_frame(frame: ProtocolFrame) -> bytes:
    """Encode one packet, including its trailing serial delimiter."""

    if frame.version != PROTOCOL_VERSION:
        raise UnsupportedVersionError(
            f"cannot encode protocol version {frame.version}"
        )
    if not 0 <= int(frame.message_type) <= 0xFF:
        raise PacketValidationError("message_type must fit in one byte")
    if not 0 <= int(frame.sequence) <= 0xFFFFFFFF:
        raise PacketValidationError("sequence must fit in uint32")
    if not 0 <= int(frame.device_uptime_ms) <= 0xFFFFFFFF:
        raise PacketValidationError("device_uptime_ms must fit in uint32")
    payload = bytes(frame.payload)
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise PacketValidationError(
            f"payload exceeds {MAX_PAYLOAD_BYTES} bytes"
        )

    packet = _HEADER.pack(
        MAGIC,
        frame.version,
        int(frame.message_type),
        int(frame.sequence),
        int(frame.device_uptime_ms),
        len(payload),
    ) + payload
    packet += _CRC.pack(zlib.crc32(packet) & 0xFFFFFFFF)
    return cobs_encode(packet) + bytes((FRAME_DELIMITER,))


def decode_frame(encoded: bytes) -> ProtocolFrame:
    """Decode and validate one COBS packet without a trailing delimiter."""

    packet = cobs_decode(encoded)
    if len(packet) < MIN_DECODED_FRAME_BYTES:
        raise PacketValidationError("packet is shorter than the fixed fields")
    if len(packet) > MAX_DECODED_FRAME_BYTES:
        raise PacketValidationError("packet exceeds the decoded size limit")

    magic, version, message_type, sequence, uptime_ms, payload_length = (
        _HEADER.unpack_from(packet)
    )
    if magic != MAGIC:
        raise PacketValidationError("packet magic does not match")
    if version != PROTOCOL_VERSION:
        raise UnsupportedVersionError(
            f"unsupported protocol version {version}"
        )
    if payload_length > MAX_PAYLOAD_BYTES:
        raise PacketValidationError("declared payload exceeds the size limit")

    expected_size = _HEADER.size + payload_length + _CRC.size
    if len(packet) != expected_size:
        raise PacketValidationError(
            f"declared payload length {payload_length} does not match packet size"
        )
    expected_crc = _CRC.unpack_from(packet, len(packet) - _CRC.size)[0]
    actual_crc = zlib.crc32(packet[:-_CRC.size]) & 0xFFFFFFFF
    if actual_crc != expected_crc:
        raise ChecksumError("packet CRC32 does not match")

    payload_start = _HEADER.size
    payload_end = payload_start + payload_length
    return ProtocolFrame(
        version=version,
        message_type=message_type,
        sequence=sequence,
        device_uptime_ms=uptime_ms,
        payload=packet[payload_start:payload_end],
    )


class Esp32FrameStream:
    """Incrementally decode a noisy serial byte stream with bounded memory."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._discarding_oversize = False
        self.decoded_frames = 0
        self.invalid_frames = 0
        self.checksum_errors = 0
        self.version_errors = 0
        self.oversize_frames = 0

    @property
    def buffered_bytes(self) -> int:
        return len(self._buffer)

    def stats(self) -> FrameStreamStats:
        return FrameStreamStats(
            decoded_frames=self.decoded_frames,
            invalid_frames=self.invalid_frames,
            checksum_errors=self.checksum_errors,
            version_errors=self.version_errors,
            oversize_frames=self.oversize_frames,
            buffered_bytes=self.buffered_bytes,
        )

    def feed(self, chunk: bytes) -> list[ProtocolFrame]:
        frames: list[ProtocolFrame] = []
        for value in bytes(chunk):
            if value == FRAME_DELIMITER:
                if self._discarding_oversize:
                    self._discarding_oversize = False
                    continue
                if not self._buffer:
                    continue
                encoded = bytes(self._buffer)
                self._buffer.clear()
                try:
                    frame = decode_frame(encoded)
                except ChecksumError:
                    self.checksum_errors += 1
                    self.invalid_frames += 1
                except UnsupportedVersionError:
                    self.version_errors += 1
                    self.invalid_frames += 1
                except ProtocolError:
                    self.invalid_frames += 1
                else:
                    self.decoded_frames += 1
                    frames.append(frame)
                continue

            if self._discarding_oversize:
                continue
            self._buffer.append(value)
            if len(self._buffer) > MAX_ENCODED_FRAME_BYTES:
                self._buffer.clear()
                self._discarding_oversize = True
                self.oversize_frames += 1
                self.invalid_frames += 1
        return frames
