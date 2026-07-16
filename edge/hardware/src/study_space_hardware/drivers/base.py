"""Uniform sensor-driver interface with bounded retries and health tracking."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from ..clock import Clock, SystemClock
from ..health import HealthTracker
from ..models import SensorHealthReport, SensorSample


class SensorError(RuntimeError):
    """Base class for diagnosable sensor failures."""


class SensorStartError(SensorError):
    pass


class SensorReadError(SensorError):
    pass


class SensorValidationError(SensorReadError):
    pass


@runtime_checkable
class SensorDriver(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def sample_rate_hz(self) -> float: ...

    def start(self) -> None: ...

    def read(self) -> SensorSample: ...

    def health(self) -> SensorHealthReport: ...

    def close(self) -> None: ...


class BaseSensorDriver(ABC):
    """Base class that prevents low-level exceptions escaping the main loop."""

    def __init__(
        self,
        name: str,
        *,
        sample_rate_hz: float,
        max_retries: int = 1,
        retry_delay_s: float = 0.01,
        offline_threshold: int = 3,
        clock: Clock | None = None,
    ) -> None:
        if sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        self._name = name
        self._sample_rate_hz = float(sample_rate_hz)
        self.max_retries = max_retries
        self.retry_delay_s = max(0.0, retry_delay_s)
        self.clock = clock or SystemClock()
        self._tracker = HealthTracker(
            name,
            offline_threshold=offline_threshold,
        )
        self._started = False
        self._closed = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def sample_rate_hz(self) -> float:
        return self._sample_rate_hz

    def start(self) -> None:
        if self._started and not self._closed:
            return
        try:
            self._start()
        except SensorError:
            self._tracker.mark_offline("sensor start failed")
            raise
        except Exception as exc:
            self._tracker.mark_offline(f"sensor start failed: {type(exc).__name__}")
            raise SensorStartError(
                f"{self.name} failed to start: {type(exc).__name__}: {exc}"
            ) from exc
        self._started = True
        self._closed = False
        self._tracker.mark_started()

    def read(self) -> SensorSample:
        if not self._started or self._closed:
            raise SensorReadError(f"{self.name} is not started")

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                sample = self._read()
                if sample.sensor != self.name:
                    raise SensorValidationError(
                        f"sample sensor {sample.sensor!r} does not match {self.name!r}"
                    )
                if not sample.valid:
                    raise SensorValidationError("driver returned an invalid sample")
                self._tracker.record_success(sample.captured_at)
                return sample
            except Exception as exc:
                last_error = exc
                self._tracker.record_failure(
                    f"{type(exc).__name__}: {exc}",
                    details={"last_attempt": attempt + 1},
                )
                if attempt < self.max_retries:
                    self.clock.sleep(self.retry_delay_s)

        assert last_error is not None
        if isinstance(last_error, SensorReadError):
            raise last_error
        raise SensorReadError(
            f"{self.name} read failed after {self.max_retries + 1} attempt(s): "
            f"{type(last_error).__name__}: {last_error}"
        ) from last_error

    def health(self) -> SensorHealthReport:
        return self._tracker.report()

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._close()
        finally:
            self._closed = True
            self._started = False

    def _start(self) -> None:
        """Optional resource initialization."""

    @abstractmethod
    def _read(self) -> SensorSample:
        raise NotImplementedError

    def _close(self) -> None:
        """Optional resource release."""
