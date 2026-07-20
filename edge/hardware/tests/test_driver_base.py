from __future__ import annotations

from study_space_hardware.clock import ManualClock
from study_space_hardware.drivers.base import BaseSensorDriver, SensorReadError
from study_space_hardware.models import SampleQuality, SensorHealth, SensorSample


class FlakyDriver(BaseSensorDriver):
    def __init__(self, failures: int, clock: ManualClock) -> None:
        super().__init__(
            "test",
            sample_rate_hz=1,
            max_retries=2,
            offline_threshold=2,
            clock=clock,
        )
        self.failures = failures
        self.close_count = 0

    def _read(self) -> SensorSample:
        if self.failures:
            self.failures -= 1
            raise OSError("temporary")
        return SensorSample(
            sensor="test",
            captured_at=self.clock.now_utc(),
            monotonic_s=self.clock.monotonic(),
            values={"value": 1},
            units={"value": "count"},
            quality=SampleQuality.VALID,
        )

    def _close(self) -> None:
        self.close_count += 1


def test_bounded_retry_recovers_and_health_returns_to_ok() -> None:
    driver = FlakyDriver(2, ManualClock())
    driver.start()
    sample = driver.read()
    assert sample.values["value"] == 1
    report = driver.health()
    assert report.status is SensorHealth.OK
    assert report.failed_reads == 2
    assert report.successful_reads == 1


def test_close_is_idempotent() -> None:
    driver = FlakyDriver(0, ManualClock())
    driver.start()
    driver.close()
    driver.close()
    assert driver.close_count == 1


def test_exhausted_retries_are_diagnosable() -> None:
    driver = FlakyDriver(10, ManualClock())
    driver.start()
    try:
        driver.read()
    except SensorReadError as exc:
        assert "failed after 3 attempt" in str(exc)
    else:
        raise AssertionError("expected SensorReadError")
    assert driver.health().status is SensorHealth.OFFLINE
