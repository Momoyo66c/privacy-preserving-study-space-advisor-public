from __future__ import annotations

import random

import pytest

from study_space_hardware.esp32_protocol import (
    MAX_ENCODED_FRAME_BYTES,
    MAX_PAYLOAD_BYTES,
    ChecksumError,
    Esp32FrameStream,
    FramingError,
    MessageType,
    PacketValidationError,
    ProtocolFrame,
    UnsupportedVersionError,
    cobs_decode,
    cobs_encode,
    decode_frame,
    encode_frame,
)


def _frame(
    *,
    message_type: int = MessageType.HEARTBEAT,
    sequence: int = 1,
    uptime_ms: int = 1_000,
    payload: bytes = b"\x1f\x00\x00\x00\x00\x00\x00\x00",
) -> ProtocolFrame:
    return ProtocolFrame(
        message_type=message_type,
        sequence=sequence,
        device_uptime_ms=uptime_ms,
        payload=payload,
    )


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"\x00",
        b"abc",
        b"a\x00b\x00c",
        bytes(range(256)),
        bytes([0x7E]) * 254,
        bytes([0x7E]) * 255,
    ],
)
def test_cobs_round_trip(raw: bytes) -> None:
    encoded = cobs_encode(raw)
    assert b"\x00" not in encoded
    assert cobs_decode(encoded) == raw


def test_cobs_rejects_invalid_frames() -> None:
    with pytest.raises(FramingError, match="empty"):
        cobs_decode(b"")
    with pytest.raises(FramingError, match="unexpected zero"):
        cobs_decode(b"\x01\x00")
    with pytest.raises(FramingError, match="beyond"):
        cobs_decode(b"\x03\x01")


def test_protocol_golden_heartbeat_vector() -> None:
    encoded = encode_frame(_frame())
    assert encoded.hex() == (
        "0850535341010101010103e803010208021f01010101010105ff9f77d300"
    )

    decoded = decode_frame(encoded[:-1])
    assert decoded == _frame()


def test_unknown_message_type_remains_forward_compatible() -> None:
    frame = _frame(message_type=0x7F, payload=b"future")
    assert decode_frame(encode_frame(frame)[:-1]) == frame


def test_checksum_corruption_is_rejected() -> None:
    encoded = bytearray(encode_frame(_frame()))
    encoded[-3] ^= 0x55
    with pytest.raises(ChecksumError):
        decode_frame(bytes(encoded[:-1]))


def test_wrong_version_is_rejected() -> None:
    encoded = bytearray(cobs_decode(encode_frame(_frame())[:-1]))
    encoded[4] = 2
    with pytest.raises(UnsupportedVersionError):
        decode_frame(cobs_encode(bytes(encoded)))


def test_declared_payload_length_is_checked() -> None:
    packet = bytearray(cobs_decode(encode_frame(_frame())[:-1]))
    packet[14:16] = (100).to_bytes(2, "little")
    with pytest.raises(PacketValidationError, match="does not match"):
        decode_frame(cobs_encode(bytes(packet)))


def test_payload_size_is_bounded() -> None:
    with pytest.raises(PacketValidationError, match="payload exceeds"):
        encode_frame(_frame(payload=b"x" * (MAX_PAYLOAD_BYTES + 1)))


def test_stream_decodes_arbitrary_chunks_and_noise() -> None:
    expected = [
        _frame(message_type=MessageType.THERMAL, sequence=10, payload=b"abc"),
        _frame(message_type=MessageType.RADAR, sequence=11, payload=b"def"),
    ]
    wire = b"not-cobs\x00" + b"".join(encode_frame(frame) for frame in expected)
    stream = Esp32FrameStream()
    actual: list[ProtocolFrame] = []
    for byte in wire:
        actual.extend(stream.feed(bytes((byte,))))

    assert actual == expected
    assert stream.stats().decoded_frames == 2
    assert stream.stats().invalid_frames == 1
    assert stream.buffered_bytes == 0


def test_stream_recovers_after_checksum_and_oversize_frames() -> None:
    corrupted = bytearray(encode_frame(_frame(sequence=20)))
    corrupted[-3] ^= 0x40
    valid = _frame(sequence=21)
    stream = Esp32FrameStream()

    assert stream.feed(bytes(corrupted)) == []
    assert stream.feed(b"x" * (MAX_ENCODED_FRAME_BYTES + 1)) == []
    assert stream.buffered_bytes == 0
    assert stream.feed(b"\x00" + encode_frame(valid)) == [valid]

    stats = stream.stats()
    assert stats.checksum_errors == 1
    assert stats.oversize_frames == 1
    assert stats.invalid_frames == 2


def test_stream_can_drop_a_partial_frame_without_resetting_counters() -> None:
    stream = Esp32FrameStream()
    assert stream.feed(encode_frame(_frame(sequence=1))) == [_frame(sequence=1)]
    stream.feed(b"partial")
    assert stream.buffered_bytes == 7

    stream.reset_partial()

    assert stream.buffered_bytes == 0
    assert stream.stats().decoded_frames == 1


def test_stream_handles_deterministic_random_chunking() -> None:
    rng = random.Random(3025)
    expected = [
        _frame(
            message_type=rng.randrange(1, 0x80),
            sequence=index,
            uptime_ms=index * 25,
            payload=rng.randbytes(rng.randrange(0, 80)),
        )
        for index in range(100)
    ]
    wire = b"".join(encode_frame(frame) for frame in expected)
    chunks: list[bytes] = []
    position = 0
    while position < len(wire):
        size = rng.randrange(1, 47)
        chunks.append(wire[position : position + size])
        position += size

    stream = Esp32FrameStream()
    actual = [frame for chunk in chunks for frame in stream.feed(chunk)]
    assert actual == expected
    assert stream.stats().invalid_frames == 0
