from __future__ import annotations

from study_space_hardware.clock import ManualClock
from study_space_hardware.drivers.ld2450 import (
    REPORT_HEADER,
    REPORT_TAIL,
    LD2450Driver,
    RadarFrameStream,
    decode_signed_magnitude_15,
    parse_report_frame,
)


def _encoded(value: int) -> bytes:
    raw = abs(value) | (0x8000 if value < 0 else 0)
    return raw.to_bytes(2, "little")


def _frame() -> bytes:
    targets = [
        _encoded(-320) + _encoded(1800) + _encoded(-14) + (120).to_bytes(2, "little"),
        _encoded(500) + _encoded(2500) + _encoded(22) + (140).to_bytes(2, "little"),
        b"\x00" * 8,
    ]
    return REPORT_HEADER + b"".join(targets) + REPORT_TAIL


class FakeSerial:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = list(chunks)
        self.closed = False

    def read(self, _: int) -> bytes:
        return self.chunks.pop(0) if self.chunks else b""

    def close(self) -> None:
        self.closed = True


def test_sign_magnitude_decoder() -> None:
    assert decode_signed_magnitude_15(0x0064) == 100
    assert decode_signed_magnitude_15(0x8064) == -100


def test_parser_extracts_three_slots_and_validity() -> None:
    targets = parse_report_frame(_frame())
    assert targets[0].x_mm == -320
    assert targets[0].y_mm == 1800
    assert targets[0].speed_cm_s == -14
    assert targets[1].valid is True
    assert targets[2].valid is False


def test_stream_recovers_from_noise_and_partial_frame() -> None:
    stream = RadarFrameStream()
    frame = _frame()
    assert stream.feed(b"noise" + frame[:10]) == []
    assert stream.feed(frame[10:]) == [frame]
    assert stream.invalid_chunks >= 1


def test_driver_reads_split_serial_frame_and_closes() -> None:
    fake = FakeSerial([_frame()[:9], _frame()[9:]])
    clock = ManualClock()
    driver = LD2450Driver(
        serial_factory=lambda: fake,
        timeout_s=0.1,
        max_retries=0,
        clock=clock,
    )
    driver.start()
    sample = driver.read()
    assert sum(target.valid for target in sample.values["targets"]) == 2
    driver.close()
    assert fake.closed is True
