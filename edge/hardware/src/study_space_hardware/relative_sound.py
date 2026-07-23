"""Device-specific ambient-margin relative calibration for HW-485 statistics."""

from __future__ import annotations

import json
import math
import os
import statistics
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


PROFILE_SCHEMA_VERSION = "1.0"
PROFILE_KIND = "hw485_relative_ambient_margin"
SENSOR_MODEL = "HW-485"
MINIMUM_ANCHOR_SAMPLES = 20
DEFAULT_NOISE_MARGIN_FRACTION = 0.10
MINIMUM_METRIC_GAP = 1e-5
MINIMUM_REFERENCE_RATIO = 1.25


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


@dataclass(frozen=True, slots=True)
class SoundMetricSummary:
    median: float
    p95: float
    maximum: float
    top_decile_median: float
    mean: float
    stddev: float

    @classmethod
    def from_values(cls, values: Sequence[float]) -> SoundMetricSummary:
        numbers = [float(value) for value in values]
        if len(numbers) < MINIMUM_ANCHOR_SAMPLES:
            raise ValueError(
                f"at least {MINIMUM_ANCHOR_SAMPLES} sound samples are required"
            )
        if not all(math.isfinite(value) and 0 <= value <= 1 for value in numbers):
            raise ValueError("sound statistics must be finite values from 0 to 1")
        top_count = max(5, math.ceil(len(numbers) * 0.10))
        ordered = sorted(numbers)
        summary = cls(
            median=float(statistics.median(numbers)),
            p95=float(_percentile(numbers, 0.95)),
            maximum=max(numbers),
            top_decile_median=float(statistics.median(ordered[-top_count:])),
            mean=float(statistics.fmean(numbers)),
            stddev=float(statistics.pstdev(numbers)),
        )
        summary.validate()
        return summary

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SoundMetricSummary:
        expected = {
            "median",
            "p95",
            "maximum",
            "top_decile_median",
            "mean",
            "stddev",
        }
        if set(value) != expected:
            raise ValueError("sound metric summary contains unknown or missing fields")
        summary = cls(**{name: float(value[name]) for name in expected})
        summary.validate()
        return summary

    def validate(self) -> None:
        values = (
            self.median,
            self.p95,
            self.maximum,
            self.top_decile_median,
            self.mean,
            self.stddev,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("sound metric summary must be finite")
        if not all(0 <= value <= 1 for value in values[:-1]):
            raise ValueError("sound metric summary values must be between 0 and 1")
        if self.stddev < 0:
            raise ValueError("sound metric standard deviation cannot be negative")
        if self.median > self.p95 or self.p95 > self.maximum:
            raise ValueError("sound metric percentiles are inconsistent")
        if self.top_decile_median > self.maximum:
            raise ValueError("sound metric high reference is inconsistent")

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SoundAnchor:
    """Aggregate RMS/peak statistics; no audio or per-chunk values are saved."""

    label: str
    sample_count: int
    rms: SoundMetricSummary
    peak: SoundMetricSummary

    @classmethod
    def from_samples(
        cls,
        label: str,
        samples: Sequence[tuple[float, float]],
    ) -> SoundAnchor:
        if label not in {"quiet", "reference"}:
            raise ValueError("sound anchor label must be quiet or reference")
        pairs = [(float(rms), float(peak)) for rms, peak in samples]
        if len(pairs) < MINIMUM_ANCHOR_SAMPLES:
            raise ValueError(
                f"at least {MINIMUM_ANCHOR_SAMPLES} sound samples are required"
            )
        anchor = cls(
            label=label,
            sample_count=len(pairs),
            rms=SoundMetricSummary.from_values([pair[0] for pair in pairs]),
            peak=SoundMetricSummary.from_values([pair[1] for pair in pairs]),
        )
        anchor.validate()
        return anchor

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SoundAnchor:
        if set(value) != {"label", "sample_count", "rms", "peak"}:
            raise ValueError("sound anchor contains unknown or missing fields")
        if not isinstance(value["rms"], Mapping) or not isinstance(
            value["peak"], Mapping
        ):
            raise ValueError("sound anchor metrics must be objects")
        anchor = cls(
            label=str(value["label"]),
            sample_count=int(value["sample_count"]),
            rms=SoundMetricSummary.from_dict(value["rms"]),
            peak=SoundMetricSummary.from_dict(value["peak"]),
        )
        anchor.validate()
        return anchor

    def validate(self) -> None:
        if self.label not in {"quiet", "reference"}:
            raise ValueError("sound anchor label must be quiet or reference")
        if self.sample_count < MINIMUM_ANCHOR_SAMPLES:
            raise ValueError(
                f"sound anchor must contain at least {MINIMUM_ANCHOR_SAMPLES} samples"
            )
        self.rms.validate()
        self.peak.validate()

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "sample_count": self.sample_count,
            "rms": self.rms.to_dict(),
            "peak": self.peak.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class RelativeSoundCalibration:
    """Map HW-485 RMS and peak statistics onto a relative 0..1 trial scale."""

    device_id: str
    created_at: str
    quiet: SoundAnchor
    reference: SoundAnchor
    noise_margin_fraction: float
    rms_floor: float
    rms_ceiling: float
    peak_floor: float
    peak_ceiling: float

    @classmethod
    def create(
        cls,
        *,
        device_id: str,
        quiet: SoundAnchor,
        reference: SoundAnchor,
        noise_margin_fraction: float = DEFAULT_NOISE_MARGIN_FRACTION,
        created_at: datetime | None = None,
    ) -> RelativeSoundCalibration:
        if quiet.label != "quiet" or reference.label != "reference":
            raise ValueError("quiet and reference anchors are required in that order")
        if not 0.05 <= noise_margin_fraction <= 0.25:
            raise ValueError("noise margin fraction must be between 0.05 and 0.25")
        rms_floor, rms_ceiling = _metric_bounds(
            quiet.rms,
            reference.rms,
            noise_margin_fraction,
            metric="RMS",
        )
        peak_floor, peak_ceiling = _metric_bounds(
            quiet.peak,
            reference.peak,
            noise_margin_fraction,
            metric="peak",
        )
        timestamp = (created_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        profile = cls(
            device_id=device_id,
            created_at=timestamp.isoformat(timespec="seconds").replace("+00:00", "Z"),
            quiet=quiet,
            reference=reference,
            noise_margin_fraction=float(noise_margin_fraction),
            rms_floor=rms_floor,
            rms_ceiling=rms_ceiling,
            peak_floor=peak_floor,
            peak_ceiling=peak_ceiling,
        )
        profile.validate()
        return profile

    def validate(self) -> None:
        if not self.device_id or not self.device_id.isascii():
            raise ValueError("calibration device_id must be a non-empty ASCII string")
        self.quiet.validate()
        self.reference.validate()
        if self.quiet.label != "quiet" or self.reference.label != "reference":
            raise ValueError("sound calibration anchors have incorrect labels")
        if not 0.05 <= self.noise_margin_fraction <= 0.25:
            raise ValueError("noise margin fraction must be between 0.05 and 0.25")
        expected_rms = _metric_bounds(
            self.quiet.rms,
            self.reference.rms,
            self.noise_margin_fraction,
            metric="RMS",
        )
        expected_peak = _metric_bounds(
            self.quiet.peak,
            self.reference.peak,
            self.noise_margin_fraction,
            metric="peak",
        )
        supplied = (
            self.rms_floor,
            self.rms_ceiling,
            self.peak_floor,
            self.peak_ceiling,
        )
        if not all(math.isfinite(value) and 0 <= value <= 1 for value in supplied):
            raise ValueError("sound calibration bounds must be finite 0..1 values")
        if not all(
            math.isclose(actual, expected, abs_tol=1e-12)
            for actual, expected in zip(
                supplied,
                (*expected_rms, *expected_peak),
                strict=True,
            )
        ):
            raise ValueError("sound calibration bounds do not match its anchors")
        try:
            parsed = datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("calibration created_at must be ISO-8601") from exc
        if parsed.tzinfo is None:
            raise ValueError("calibration created_at must include a timezone")

    @staticmethod
    def _map(value: float, floor: float, ceiling: float) -> float:
        number = float(value)
        if not math.isfinite(number) or not 0 <= number <= 1:
            raise ValueError("sound statistic must be finite and between 0 and 1")
        return min(1.0, max(0.0, (number - floor) / (ceiling - floor)))

    def map_rms(self, value: float) -> float:
        return self._map(value, self.rms_floor, self.rms_ceiling)

    def map_peak(self, value: float) -> float:
        return self._map(value, self.peak_floor, self.peak_ceiling)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "kind": PROFILE_KIND,
            "sensor_model": SENSOR_MODEL,
            "device_id": self.device_id,
            "created_at": self.created_at,
            "method": "quiet_p95_plus_margin_to_reference_top_decile",
            "noise_margin_fraction": self.noise_margin_fraction,
            "calibrated_db": False,
            "rms_floor": self.rms_floor,
            "rms_ceiling": self.rms_ceiling,
            "peak_floor": self.peak_floor,
            "peak_ceiling": self.peak_ceiling,
            "quiet": self.quiet.to_dict(),
            "reference": self.reference.to_dict(),
        }


def _metric_bounds(
    quiet: SoundMetricSummary,
    reference: SoundMetricSummary,
    margin_fraction: float,
    *,
    metric: str,
) -> tuple[float, float]:
    baseline = quiet.p95
    ceiling = reference.top_decile_median
    gap = ceiling - baseline
    if gap < MINIMUM_METRIC_GAP:
        raise ValueError(
            f"{metric} reference is too close to ambient noise; "
            "repeat the reference with a clearer sound response"
        )
    if baseline > 0 and ceiling < baseline * MINIMUM_REFERENCE_RATIO:
        raise ValueError(
            f"{metric} reference must be at least "
            f"{MINIMUM_REFERENCE_RATIO:.2f}x the ambient p95"
        )
    floor = baseline + gap * margin_fraction
    return float(floor), float(ceiling)


def calibration_from_dict(
    value: Mapping[str, Any],
    *,
    expected_device_id: str | None = None,
) -> RelativeSoundCalibration:
    expected = {
        "schema_version",
        "kind",
        "sensor_model",
        "device_id",
        "created_at",
        "method",
        "noise_margin_fraction",
        "calibrated_db",
        "rms_floor",
        "rms_ceiling",
        "peak_floor",
        "peak_ceiling",
        "quiet",
        "reference",
    }
    if set(value) != expected:
        raise ValueError("relative-sound profile contains unknown or missing fields")
    if value["schema_version"] != PROFILE_SCHEMA_VERSION:
        raise ValueError("unsupported relative-sound profile schema_version")
    if value["kind"] != PROFILE_KIND or value["sensor_model"] != SENSOR_MODEL:
        raise ValueError("profile is not an HW-485 relative-sound calibration")
    if value["method"] != "quiet_p95_plus_margin_to_reference_top_decile":
        raise ValueError("unsupported relative-sound calibration method")
    if value["calibrated_db"] is not False:
        raise ValueError("relative-sound profile cannot claim calibrated dB")
    if not isinstance(value["quiet"], Mapping) or not isinstance(
        value["reference"], Mapping
    ):
        raise ValueError("relative-sound profile anchors must be objects")
    profile = RelativeSoundCalibration(
        device_id=str(value["device_id"]),
        created_at=str(value["created_at"]),
        quiet=SoundAnchor.from_dict(value["quiet"]),
        reference=SoundAnchor.from_dict(value["reference"]),
        noise_margin_fraction=float(value["noise_margin_fraction"]),
        rms_floor=float(value["rms_floor"]),
        rms_ceiling=float(value["rms_ceiling"]),
        peak_floor=float(value["peak_floor"]),
        peak_ceiling=float(value["peak_ceiling"]),
    )
    profile.validate()
    if expected_device_id is not None and profile.device_id != expected_device_id:
        raise ValueError(
            "relative-sound profile belongs to a different device: "
            f"{profile.device_id}"
        )
    return profile


def load_calibration(
    path: str | Path,
    *,
    expected_device_id: str | None = None,
) -> RelativeSoundCalibration:
    profile_path = Path(path).expanduser()
    try:
        value = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"cannot read relative-sound profile: {profile_path}"
        ) from exc
    if not isinstance(value, Mapping):
        raise ValueError("relative-sound profile root must be an object")
    return calibration_from_dict(value, expected_device_id=expected_device_id)


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def save_calibration(path: str | Path, profile: RelativeSoundCalibration) -> None:
    profile.validate()
    _atomic_write_json(Path(path), profile.to_dict())


def save_quiet_staging(
    path: str | Path,
    *,
    device_id: str,
    quiet: SoundAnchor,
    captured_at: datetime | None = None,
) -> None:
    if quiet.label != "quiet":
        raise ValueError("quiet staging requires a quiet anchor")
    timestamp = (captured_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    _atomic_write_json(
        Path(path),
        {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "kind": "hw485_relative_quiet_staging",
            "sensor_model": SENSOR_MODEL,
            "device_id": device_id,
            "captured_at": timestamp.isoformat(timespec="seconds").replace(
                "+00:00",
                "Z",
            ),
            "quiet": quiet.to_dict(),
        },
    )


def load_quiet_staging(
    path: str | Path,
    *,
    expected_device_id: str,
) -> SoundAnchor:
    staging_path = Path(path).expanduser()
    try:
        value = json.loads(staging_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read quiet-anchor staging: {staging_path}") from exc
    if not isinstance(value, Mapping):
        raise ValueError("quiet-anchor staging root must be an object")
    expected = {
        "schema_version",
        "kind",
        "sensor_model",
        "device_id",
        "captured_at",
        "quiet",
    }
    if set(value) != expected:
        raise ValueError("quiet-anchor staging contains unknown or missing fields")
    if (
        value["schema_version"] != PROFILE_SCHEMA_VERSION
        or value["kind"] != "hw485_relative_quiet_staging"
        or value["sensor_model"] != SENSOR_MODEL
    ):
        raise ValueError("invalid quiet-anchor staging metadata")
    if value["device_id"] != expected_device_id:
        raise ValueError("quiet-anchor staging belongs to a different device")
    if not isinstance(value["quiet"], Mapping):
        raise ValueError("quiet-anchor staging value must be an object")
    quiet = SoundAnchor.from_dict(value["quiet"])
    if quiet.label != "quiet":
        raise ValueError("quiet-anchor staging contains the wrong anchor label")
    return quiet
