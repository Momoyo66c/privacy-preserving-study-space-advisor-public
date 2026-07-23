"""Command line capture and comparison for aggregate HW-485 diagnostics."""

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
from .models import SensorSample
from .sound_diagnostic import (
    MINIMUM_DIAGNOSTIC_WINDOWS,
    SoundDiagnosticSnapshot,
    compare_snapshots,
    load_snapshot,
    save_snapshot,
)


def _capture_samples(
    config: HardwareConfig,
    *,
    sample_count: int,
    warmup_count: int,
) -> list[SensorSample]:
    if config.simulator.enabled or config.transport.mode != "esp32_hub":
        raise ValueError("sound diagnostics require a real ESP32 Hub config")
    drivers = build_real_drivers(config, clock=SystemClock())
    sound = drivers.get("sound")
    if sound is None:
        raise ValueError("sound sensor must be enabled for diagnostics")

    accepted = 0
    samples: list[SensorSample] = []
    deadline = time.monotonic() + max(
        60.0,
        (sample_count + warmup_count) * 1.25,
    )
    try:
        sound.start()
        while len(samples) < sample_count:
            try:
                sample = sound.read()
            except SensorReadError as exc:
                if time.monotonic() >= deadline:
                    raise SensorReadError(
                        "timed out before enough HW-485 diagnostic windows "
                        f"were collected ({len(samples)}/{sample_count})"
                    ) from exc
                continue
            accepted += 1
            if accepted <= warmup_count:
                continue
            samples.append(sample)
    finally:
        sound.close()
    return samples


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Summarize the HW-485 firmware's high-rate ADC windows without "
            "saving audio or individual window values."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture_parser = subparsers.add_parser(
        "capture",
        help="capture one aggregate-only quiet or reference snapshot",
    )
    capture_parser.add_argument("--config", required=True)
    capture_parser.add_argument(
        "--label",
        choices=("quiet", "reference"),
        required=True,
    )
    capture_parser.add_argument("--output", required=True)
    capture_parser.add_argument("--samples", type=int, default=32)
    capture_parser.add_argument("--warmup-samples", type=int, default=8)

    compare_parser = subparsers.add_parser(
        "compare",
        help="compare saved quiet and reference aggregate snapshots",
    )
    compare_parser.add_argument("--quiet", required=True)
    compare_parser.add_argument("--reference", required=True)
    compare_parser.add_argument("--device-id")

    args = parser.parse_args(argv)
    if args.command == "compare":
        quiet = load_snapshot(
            args.quiet,
            expected_device_id=args.device_id,
            expected_label="quiet",
        )
        reference = load_snapshot(
            args.reference,
            expected_device_id=args.device_id,
            expected_label="reference",
        )
        print(
            json.dumps(
                compare_snapshots(quiet, reference),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.samples < MINIMUM_DIAGNOSTIC_WINDOWS:
        parser.error(
            f"--samples must be at least {MINIMUM_DIAGNOSTIC_WINDOWS}"
        )
    if args.warmup_samples < 0:
        parser.error("--warmup-samples cannot be negative")

    config = load_config(args.config)
    samples = _capture_samples(
        config,
        sample_count=args.samples,
        warmup_count=args.warmup_samples,
    )
    snapshot = SoundDiagnosticSnapshot.from_samples(
        device_id=config.device_id,
        label=args.label,
        samples=samples,
    )
    save_snapshot(args.output, snapshot)
    print(
        json.dumps(
            {
                "ok": True,
                "snapshot_path": str(Path(args.output).expanduser()),
                "snapshot": snapshot.to_dict(),
                "note": (
                    "firmware high-rate aggregate windows only; no audio or "
                    "individual window values were saved"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0
