from __future__ import annotations

import math

from study_space_hardware.clock import ManualClock
from study_space_hardware.drivers.sound_level import (
    SoundLevelDriver,
    summarize_audio,
)


def test_audio_summary() -> None:
    result = summarize_audio([1.0, -1.0, 0.0, 0.0])
    assert result["rms"] == math.sqrt(0.5)
    assert result["peak"] == 1.0


def test_driver_only_returns_statistics() -> None:
    driver = SoundLevelDriver(
        chunk_reader=lambda: [0.1, -0.1, 0.2, -0.2],
        clock=ManualClock(),
    )
    driver.start()
    sample = driver.read()
    assert set(sample.values) == {
        "rms",
        "std",
        "peak",
        "raw_audio_persisted",
        "chunk_frames",
    }
    assert sample.values["raw_audio_persisted"] is False
