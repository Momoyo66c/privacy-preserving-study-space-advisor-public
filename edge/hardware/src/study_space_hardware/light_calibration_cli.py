"""Command line workflow for non-lux HW-486 relative calibration."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Sequence

from .bootstrap import build_real_drivers
from .clock import SystemClock
from .config import HardwareConfig, load_config
from .drivers.base import SensorReadError
from .relative_light import (
    LightAnchor,
    RelativeLightCalibration,
    load_calibration,
    load_dark_staging,
    save_calibration,
    save_dark_staging,
)


def _capture_anchor(
    config: HardwareConfig,
    *,
    label: str,
    sample_count: int,
) -> LightAnchor:
    if config.simulator.enabled or config.transport.mode != "esp32_hub":
        raise ValueError("relative calibration requires a real ESP32 Hub config")
    drivers = build_real_drivers(config, clock=SystemClock())
    light = drivers.get("light")
    if light is None:
        raise ValueError("light sensor must be enabled for relative calibration")
    values: list[int] = []
    deadline = time.monotonic() + max(30.0, sample_count * 4.0)
    try:
        light.start()
        while len(values) < sample_count:
            try:
                sample = light.read()
            except SensorReadError as exc:
                if time.monotonic() >= deadline:
                    raise SensorReadError(
                        "timed out before enough HW-486 calibration samples "
                        f"were collected ({len(values)}/{sample_count})"
                    ) from exc
                continue
            values.append(int(sample.values["light_adc_raw"]))
    finally:
        light.close()
    return LightAnchor.from_samples(label, values)


def _anchor_result(anchor: LightAnchor) -> dict[str, object]:
    return {
        "ok": True,
        "anchor": anchor.to_dict(),
        "note": "aggregate statistics only; individual ADC readings were not saved",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Calibrate HW-486 to a device-specific relative 0..1 scale. "
            "This does not produce lux."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    dark_parser = subparsers.add_parser(
        "capture-dark",
        help="capture the room-specific dark reference",
    )
    dark_parser.add_argument("--config", required=True)
    dark_parser.add_argument("--output", required=True)
    dark_parser.add_argument("--samples", type=int, default=12)

    bright_parser = subparsers.add_parser(
        "capture-bright",
        help="capture the bright reference and create the final profile",
    )
    bright_parser.add_argument("--config", required=True)
    bright_parser.add_argument("--staging", required=True)
    bright_parser.add_argument("--output", required=True)
    bright_parser.add_argument("--samples", type=int, default=12)

    status_parser = subparsers.add_parser(
        "status",
        help="validate and summarize a relative-light profile",
    )
    status_parser.add_argument("--profile", required=True)
    status_parser.add_argument("--device-id")

    args = parser.parse_args(argv)
    if args.command in {"capture-dark", "capture-bright"} and args.samples < 5:
        parser.error("--samples must be at least 5")

    if args.command == "status":
        profile = load_calibration(
            args.profile,
            expected_device_id=args.device_id,
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "profile": str(Path(args.profile).expanduser()),
                    "device_id": profile.device_id,
                    "created_at": profile.created_at,
                    "method": "median_dark_bright_clamped",
                    "direction": profile.direction,
                    "span_adc": profile.span_adc,
                    "dark_median_adc": profile.dark.median_adc,
                    "bright_median_adc": profile.bright.median_adc,
                    "calibrated_lux": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    config = load_config(args.config)
    if args.command == "capture-dark":
        dark = _capture_anchor(
            config,
            label="dark",
            sample_count=args.samples,
        )
        save_dark_staging(
            args.output,
            device_id=config.device_id,
            dark=dark,
        )
        result = _anchor_result(dark)
        result["staging_path"] = str(Path(args.output).expanduser())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    dark = load_dark_staging(
        args.staging,
        expected_device_id=config.device_id,
    )
    bright = _capture_anchor(
        config,
        label="bright",
        sample_count=args.samples,
    )
    profile = RelativeLightCalibration.create(
        device_id=config.device_id,
        dark=dark,
        bright=bright,
    )
    save_calibration(args.output, profile)
    result = _anchor_result(bright)
    result.update(
        {
            "profile_path": str(Path(args.output).expanduser()),
            "direction": profile.direction,
            "span_adc": profile.span_adc,
            "calibrated_lux": False,
        }
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
