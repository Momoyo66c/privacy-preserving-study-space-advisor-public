"""Sound-intensity statistics with no raw-audio persistence."""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable, Iterable
from typing import Any

from .base import BaseSensorDriver, SensorStartError, SensorValidationError
from ..clock import Clock
from ..models import SampleQuality, SensorSample


def summarize_audio(values: Iterable[float]) -> dict[str, float]:
    samples = [float(value) for value in values]
    if not samples:
        raise SensorValidationError("audio chunk is empty")
    if not all(math.isfinite(value) for value in samples):
        raise SensorValidationError("audio chunk contains non-finite values")
    mean_square = sum(value * value for value in samples) / len(samples)
    return {
        "rms": math.sqrt(mean_square),
        "std": statistics.pstdev(samples),
        "peak": max(abs(value) for value in samples),
    }


def _flatten_audio(chunk: Any) -> list[float]:
    if hasattr(chunk, "ravel"):
        return [float(value) for value in chunk.ravel().tolist()]
    if isinstance(chunk, (list, tuple)):
        flattened: list[float] = []
        for item in chunk:
            if isinstance(item, (list, tuple)):
                flattened.extend(float(value) for value in item)
            else:
                flattened.append(float(item))
        return flattened
    return [float(value) for value in chunk]


class SoundLevelDriver(BaseSensorDriver):
    def __init__(
        self,
        *,
        sample_rate_hz: float = 4.0,
        audio_sample_rate_hz: int = 8_000,
        chunk_seconds: float = 0.1,
        channels: int = 1,
        chunk_reader: Callable[[], Any] | None = None,
        max_retries: int = 1,
        offline_threshold: int = 3,
        clock: Clock | None = None,
    ) -> None:
        super().__init__(
            "sound",
            sample_rate_hz=sample_rate_hz,
            max_retries=max_retries,
            offline_threshold=offline_threshold,
            clock=clock,
        )
        self.audio_sample_rate_hz = int(audio_sample_rate_hz)
        self.chunk_seconds = float(chunk_seconds)
        self.channels = int(channels)
        self._chunk_reader = chunk_reader
        self._stream: Any = None
        self.raw_audio_persisted = False

    @property
    def block_frames(self) -> int:
        return max(1, round(self.audio_sample_rate_hz * self.chunk_seconds))

    def _start(self) -> None:
        if self._chunk_reader is not None:
            return
        try:
            import sounddevice
        except ImportError as exc:
            raise SensorStartError(
                "sounddevice is required for the real sound-level driver"
            ) from exc
        self._stream = sounddevice.InputStream(
            samplerate=self.audio_sample_rate_hz,
            channels=self.channels,
            dtype="float32",
            blocksize=self.block_frames,
        )
        self._stream.start()

    def _read(self) -> SensorSample:
        if self._chunk_reader is not None:
            raw_chunk = self._chunk_reader()
        else:
            raw_chunk, overflowed = self._stream.read(self.block_frames)
            if overflowed:
                self._tracker.details["input_overflow_count"] = (
                    self._tracker.details.get("input_overflow_count", 0) + 1
                )
        flattened = _flatten_audio(raw_chunk)
        try:
            summary = summarize_audio(flattened)
        finally:
            del flattened
            del raw_chunk
        return SensorSample(
            sensor=self.name,
            captured_at=self.clock.now_utc(),
            monotonic_s=self.clock.monotonic(),
            values={
                **summary,
                "raw_audio_persisted": False,
                "chunk_frames": self.block_frames,
            },
            units={"rms": "normalized", "std": "normalized", "peak": "normalized"},
            quality=SampleQuality.VALID,
            source="sound-intensity",
        )

    def _close(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
        self._stream = None
