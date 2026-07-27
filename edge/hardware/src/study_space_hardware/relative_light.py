"""Device-specific two-point relative calibration for the HW-486 LDR module."""

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
PROFILE_KIND = "hw486_relative_two_point"
SENSOR_MODEL = "HW-486"
MINIMUM_ANCHOR_SAMPLES = 5
MINIMUM_ANCHOR_SPAN_ADC = 64.0


@dataclass(frozen=True, slots=True)
class LightAnchor:
    """Aggregate-only anchor statistics; individual readings are not persisted."""

    label: str
    sample_count: int
    median_adc: float
    mean_adc: float
    minimum_adc: int
    maximum_adc: int
    stddev_adc: float

    @classmethod
    def from_samples(cls, label: str, samples: Sequence[int]) -> LightAnchor:
        if label not in {"dark", "bright"}:
            raise ValueError("light anchor label must be dark or bright")
        values = [int(value) for value in samples]
        if len(values) < MINIMUM_ANCHOR_SAMPLES:
            raise ValueError(
                f"at least {MINIMUM_ANCHOR_SAMPLES} light samples are required"
            )
        if any(value < 0 or value > 4095 for value in values):
            raise ValueError("light anchor samples must be ADC values from 0 to 4095")
        return cls(
            label=label,
            sample_count=len(values),
            median_adc=float(statistics.median(values)),
            mean_adc=float(statistics.fmean(values)),
            minimum_adc=min(values),
            maximum_adc=max(values),
            stddev_adc=float(statistics.pstdev(values)),
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> LightAnchor:
        expected = {
            "label",
            "sample_count",
            "median_adc",
            "mean_adc",
            "minimum_adc",
            "maximum_adc",
            "stddev_adc",
        }
        if set(value) != expected:
            raise ValueError("light anchor contains unknown or missing fields")
        anchor = cls(
            label=str(value["label"]),
            sample_count=int(value["sample_count"]),
            median_adc=float(value["median_adc"]),
            mean_adc=float(value["mean_adc"]),
            minimum_adc=int(value["minimum_adc"]),
            maximum_adc=int(value["maximum_adc"]),
            stddev_adc=float(value["stddev_adc"]),
        )
        anchor.validate()
        return anchor

    def validate(self) -> None:
        if self.label not in {"dark", "bright"}:
            raise ValueError("light anchor label must be dark or bright")
        if self.sample_count < MINIMUM_ANCHOR_SAMPLES:
            raise ValueError(
                f"light anchor must contain at least {MINIMUM_ANCHOR_SAMPLES} samples"
            )
        numeric = (
            self.median_adc,
            self.mean_adc,
            self.stddev_adc,
        )
        if not all(math.isfinite(value) for value in numeric):
            raise ValueError("light anchor statistics must be finite")
        if not 0 <= self.median_adc <= 4095 or not 0 <= self.mean_adc <= 4095:
            raise ValueError("light anchor center must be between 0 and 4095")
        if not 0 <= self.minimum_adc <= self.maximum_adc <= 4095:
            raise ValueError("light anchor range must be between 0 and 4095")
        if self.stddev_adc < 0:
            raise ValueError("light anchor standard deviation cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RelativeLightCalibration:
    """Map an HW-486 ADC value onto a room-specific relative 0..1 scale."""

    device_id: str
    created_at: str
    dark: LightAnchor
    bright: LightAnchor
    direction: str

    @classmethod
    def create(
        cls,
        *,
        device_id: str,
        dark: LightAnchor,
        bright: LightAnchor,
        created_at: datetime | None = None,
    ) -> RelativeLightCalibration:
        if dark.label != "dark" or bright.label != "bright":
            raise ValueError("dark and bright anchors are required in that order")
        direction = (
            "increasing"
            if bright.median_adc > dark.median_adc
            else "decreasing"
        )
        timestamp = (created_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        profile = cls(
            device_id=device_id,
            created_at=timestamp.isoformat(timespec="seconds").replace("+00:00", "Z"),
            dark=dark,
            bright=bright,
            direction=direction,
        )
        profile.validate()
        return profile

    @property
    def span_adc(self) -> float:
        return abs(self.bright.median_adc - self.dark.median_adc)

    def validate(self) -> None:
        if not self.device_id or not self.device_id.isascii():
            raise ValueError("calibration device_id must be a non-empty ASCII string")
        self.dark.validate()
        self.bright.validate()
        if self.dark.label != "dark" or self.bright.label != "bright":
            raise ValueError("calibration anchors have incorrect labels")
        expected_direction = (
            "increasing"
            if self.bright.median_adc > self.dark.median_adc
            else "decreasing"
        )
        if self.direction != expected_direction:
            raise ValueError("calibration direction does not match its anchors")
        if self.span_adc < MINIMUM_ANCHOR_SPAN_ADC:
            raise ValueError(
                "dark and bright anchors are too close; "
                f"need at least {MINIMUM_ANCHOR_SPAN_ADC:g} ADC counts"
            )
        try:
            parsed = datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("calibration created_at must be ISO-8601") from exc
        if parsed.tzinfo is None:
            raise ValueError("calibration created_at must include a timezone")

    def map_adc(self, adc_raw: int | float) -> float:
        value = float(adc_raw)
        if not math.isfinite(value) or not 0 <= value <= 4095:
            raise ValueError("light ADC value must be finite and between 0 and 4095")
        numerator = (
            value - self.dark.median_adc
            if self.direction == "increasing"
            else self.dark.median_adc - value
        )
        return min(1.0, max(0.0, numerator / self.span_adc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "kind": PROFILE_KIND,
            "sensor_model": SENSOR_MODEL,
            "device_id": self.device_id,
            "created_at": self.created_at,
            "method": "median_dark_bright_clamped",
            "direction": self.direction,
            "span_adc": self.span_adc,
            "dark": self.dark.to_dict(),
            "bright": self.bright.to_dict(),
        }


def calibration_from_dict(
    value: Mapping[str, Any],
    *,
    expected_device_id: str | None = None,
) -> RelativeLightCalibration:
    expected = {
        "schema_version",
        "kind",
        "sensor_model",
        "device_id",
        "created_at",
        "method",
        "direction",
        "span_adc",
        "dark",
        "bright",
    }
    if set(value) != expected:
        raise ValueError("relative-light profile contains unknown or missing fields")
    if value["schema_version"] != PROFILE_SCHEMA_VERSION:
        raise ValueError("unsupported relative-light profile schema_version")
    if value["kind"] != PROFILE_KIND or value["sensor_model"] != SENSOR_MODEL:
        raise ValueError("profile is not an HW-486 relative-light calibration")
    if value["method"] != "median_dark_bright_clamped":
        raise ValueError("unsupported relative-light calibration method")
    if not isinstance(value["dark"], Mapping) or not isinstance(
        value["bright"], Mapping
    ):
        raise ValueError("relative-light profile anchors must be objects")
    profile = RelativeLightCalibration(
        device_id=str(value["device_id"]),
        created_at=str(value["created_at"]),
        dark=LightAnchor.from_dict(value["dark"]),
        bright=LightAnchor.from_dict(value["bright"]),
        direction=str(value["direction"]),
    )
    profile.validate()
    supplied_span = float(value["span_adc"])
    if not math.isfinite(supplied_span) or not math.isclose(
        supplied_span,
        profile.span_adc,
        abs_tol=1e-6,
    ):
        raise ValueError("relative-light profile span does not match its anchors")
    if expected_device_id is not None and profile.device_id != expected_device_id:
        raise ValueError(
            "relative-light profile belongs to a different device: "
            f"{profile.device_id}"
        )
    return profile


def load_calibration(
    path: str | Path,
    *,
    expected_device_id: str | None = None,
) -> RelativeLightCalibration:
    profile_path = Path(path).expanduser()
    try:
        value = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"cannot read relative-light profile: {profile_path}"
        ) from exc
    if not isinstance(value, Mapping):
        raise ValueError("relative-light profile root must be an object")
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


def save_calibration(
    path: str | Path,
    profile: RelativeLightCalibration,
) -> None:
    profile.validate()
    _atomic_write_json(Path(path), profile.to_dict())


def save_dark_staging(
    path: str | Path,
    *,
    device_id: str,
    dark: LightAnchor,
    captured_at: datetime | None = None,
) -> None:
    if dark.label != "dark":
        raise ValueError("dark staging requires a dark anchor")
    timestamp = (captured_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    _atomic_write_json(
        Path(path),
        {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "kind": "hw486_relative_dark_staging",
            "sensor_model": SENSOR_MODEL,
            "device_id": device_id,
            "captured_at": timestamp.isoformat(timespec="seconds").replace(
                "+00:00",
                "Z",
            ),
            "dark": dark.to_dict(),
        },
    )


def load_dark_staging(
    path: str | Path,
    *,
    expected_device_id: str,
) -> LightAnchor:
    staging_path = Path(path).expanduser()
    try:
        value = json.loads(staging_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read dark-anchor staging: {staging_path}") from exc
    if not isinstance(value, Mapping):
        raise ValueError("dark-anchor staging root must be an object")
    expected = {
        "schema_version",
        "kind",
        "sensor_model",
        "device_id",
        "captured_at",
        "dark",
    }
    if set(value) != expected:
        raise ValueError("dark-anchor staging contains unknown or missing fields")
    if (
        value["schema_version"] != PROFILE_SCHEMA_VERSION
        or value["kind"] != "hw486_relative_dark_staging"
        or value["sensor_model"] != SENSOR_MODEL
    ):
        raise ValueError("invalid dark-anchor staging metadata")
    if value["device_id"] != expected_device_id:
        raise ValueError("dark-anchor staging belongs to a different device")
    if not isinstance(value["dark"], Mapping):
        raise ValueError("dark-anchor staging value must be an object")
    dark = LightAnchor.from_dict(value["dark"])
    if dark.label != "dark":
        raise ValueError("dark-anchor staging contains the wrong anchor label")
    return dark
