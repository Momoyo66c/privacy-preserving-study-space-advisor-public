"""Two-stage, timeout-tolerant HW-485 relative calibration CLI."""

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
from .relative_sound import (
    DEFAULT_NOISE_MARGIN_FRACTION,
    MINIMUM_ANCHOR_SAMPLES,
    RelativeSoundCalibration,
    SoundAnchor,
    load_calibration,
    load_quiet_staging,
    save_calibration,
    save_quiet_staging,
)


def _capture_anchor(
    config: HardwareConfig,
    *,
    label: str,
    sample_count: int,
    warmup_count: int,
) -> SoundAnchor:
    if config.simulator.enabled or config.transport.mode != "esp32_hub":
        raise ValueError("relative calibration requires a real ESP32 Hub config")
    drivers = build_real_drivers(config, clock=SystemClock())
    sound = drivers.get("sound")
    if sound is None:
        raise ValueError("sound sensor must be enabled for relative calibration")
    accepted = 0
    samples: list[tuple[float, float]] = []
    deadline = time.monotonic() + max(60.0, (sample_count + warmup_count) * 1.25)
    try:
        sound.start()
        while len(samples) < sample_count:
            try:
                sample = sound.read()
            except SensorReadError as exc:
                if time.monotonic() >= deadline:
                    raise SensorReadError(
                        "timed out before enough HW-485 calibration samples "
                        f"were collected ({len(samples)}/{sample_count})"
                    ) from exc
                continue
            accepted += 1
            if accepted <= warmup_count:
                continue
            rms = float(
                sample.values.get(
                    "rms_sensor_normalized",
                    sample.values["rms"],
                )
            )
            peak = float(
                sample.values.get(
                    "peak_sensor_normalized",
                    sample.values["peak"],
                )
            )
            samples.append((rms, peak))
    finally:
        sound.close()
    return SoundAnchor.from_samples(label, samples)


def _anchor_result(anchor: SoundAnchor) -> dict[str, object]:
    return {
        "ok": True,
        "anchor": anchor.to_dict(),
        "note": (
            "aggregate RMS/peak statistics only; no audio or per-chunk values "
            "were saved"
        ),
        "calibrated_db": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Calibrate HW-485 to a device-specific relative 0..1 scale with "
            "ambient-noise margin. This does not produce dB."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    quiet_parser = subparsers.add_parser(
        "capture-quiet",
        help="capture the current ambient-noise reference",
    )
    quiet_parser.add_argument("--config", required=True)
    quiet_parser.add_argument("--output", required=True)
    quiet_parser.add_argument("--samples", type=int, default=32)
    quiet_parser.add_argument("--warmup-samples", type=int, default=8)

    preflight_parser = subparsers.add_parser(
        "preflight",
        help="read and summarize HW-485 safely without saving an anchor",
    )
    preflight_parser.add_argument("--config", required=True)
    preflight_parser.add_argument("--samples", type=int, default=20)
    preflight_parser.add_argument("--warmup-samples", type=int, default=8)

    reference_parser = subparsers.add_parser(
        "capture-reference",
        help="capture a controlled audible reference and create a trial profile",
    )
    reference_parser.add_argument("--config", required=True)
    reference_parser.add_argument("--staging", required=True)
    reference_parser.add_argument("--output", required=True)
    reference_parser.add_argument("--samples", type=int, default=32)
    reference_parser.add_argument("--warmup-samples", type=int, default=8)
    reference_parser.add_argument(
        "--noise-margin-fraction",
        type=float,
        default=DEFAULT_NOISE_MARGIN_FRACTION,
    )

    status_parser = subparsers.add_parser(
        "status",
        help="validate and summarize a relative-sound profile",
    )
    status_parser.add_argument("--profile", required=True)
    status_parser.add_argument("--device-id")

    args = parser.parse_args(argv)
    if args.command in {"preflight", "capture-quiet", "capture-reference"}:
        if args.samples < MINIMUM_ANCHOR_SAMPLES:
            parser.error(f"--samples must be at least {MINIMUM_ANCHOR_SAMPLES}")
        if args.warmup_samples < 0:
            parser.error("--warmup-samples cannot be negative")

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
                    "method": "quiet_p95_plus_margin_to_reference_top_decile",
                    "noise_margin_fraction": profile.noise_margin_fraction,
                    "rms_floor": profile.rms_floor,
                    "rms_ceiling": profile.rms_ceiling,
                    "peak_floor": profile.peak_floor,
                    "peak_ceiling": profile.peak_ceiling,
                    "calibrated_db": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    config = load_config(args.config)
    if args.command == "preflight":
        diagnostic = _capture_anchor(
            config,
            label="quiet",
            sample_count=args.samples,
            warmup_count=args.warmup_samples,
        )
        result = _anchor_result(diagnostic)
        result["saved"] = False
        result["diagnostic_only"] = True
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "capture-quiet":
        quiet = _capture_anchor(
            config,
            label="quiet",
            sample_count=args.samples,
            warmup_count=args.warmup_samples,
        )
        save_quiet_staging(
            args.output,
            device_id=config.device_id,
            quiet=quiet,
        )
        result = _anchor_result(quiet)
        result["staging_path"] = str(Path(args.output).expanduser())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    quiet = load_quiet_staging(
        args.staging,
        expected_device_id=config.device_id,
    )
    reference = _capture_anchor(
        config,
        label="reference",
        sample_count=args.samples,
        warmup_count=args.warmup_samples,
    )
    profile = RelativeSoundCalibration.create(
        device_id=config.device_id,
        quiet=quiet,
        reference=reference,
        noise_margin_fraction=args.noise_margin_fraction,
    )
    save_calibration(args.output, profile)
    result = _anchor_result(reference)
    result.update(
        {
            "profile_path": str(Path(args.output).expanduser()),
            "noise_margin_fraction": profile.noise_margin_fraction,
            "rms_floor": profile.rms_floor,
            "rms_ceiling": profile.rms_ceiling,
            "peak_floor": profile.peak_floor,
            "peak_ceiling": profile.peak_ceiling,
        }
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
