"""Command-line entry points for probing, simulation and offline collection."""

from __future__ import annotations

import argparse
import json
import logging
import math
from dataclasses import replace
from typing import Sequence

from .bootstrap import build_orchestrator
from .clock import ManualClock, SystemClock
from .config import HardwareConfig, load_config
from .models import RadarTarget, SensorSample
from .storage import SessionWriter, enforce_session_retention


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s level=%(levelname)s logger=%(name)s message=%(message)s",
    )


def _with_overrides(
    config: HardwareConfig,
    *,
    room_id: str | None = None,
    scenario: str | None = None,
) -> HardwareConfig:
    simulator = (
        replace(config.simulator, scenario=scenario)
        if scenario is not None
        else config.simulator
    )
    updated = replace(
        config,
        room_id=room_id or config.room_id,
        simulator=simulator,
    )
    updated.validate()
    return updated


def _sample_summary(sample: SensorSample) -> dict[str, object]:
    summary: dict[str, object] = {
        "sensor": sample.sensor,
        "captured_at": sample.captured_at.isoformat(),
        "quality": sample.quality.value,
        "source": sample.source,
    }
    if sample.sensor == "thermal":
        values = tuple(sample.values["temperatures_c"])
        summary["frame_shape"] = [
            sample.values["height"],
            sample.values["width"],
        ]
        summary["temperature_min_c"] = min(values)
        summary["temperature_max_c"] = max(values)
    elif sample.sensor == "radar":
        targets = sample.values.get("targets", ())
        summary["active_targets"] = sum(
            isinstance(target, RadarTarget) and target.valid for target in targets
        )
    elif sample.sensor == "sound":
        summary["rms"] = sample.values["rms"]
        summary["peak"] = sample.values["peak"]
        summary["raw_audio_persisted"] = False
    else:
        summary["values"] = {
            key: value
            for key, value in sample.values.items()
            if key != "temperatures_c"
        }
    return summary


def simulator_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic sensor simulation")
    parser.add_argument("--config", required=True)
    parser.add_argument("--scenario")
    parser.add_argument("--windows", type=int, default=1)
    parser.add_argument("--realtime", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    if args.windows < 1:
        parser.error("--windows must be positive")
    config = _with_overrides(load_config(args.config), scenario=args.scenario)
    config = replace(config, simulator=replace(config.simulator, enabled=True))
    clock = SystemClock() if args.realtime else ManualClock()
    orchestrator = build_orchestrator(config, clock=clock)
    try:
        for _ in range(args.windows):
            window = orchestrator.run_window()
            print(json.dumps(window.payload, ensure_ascii=False, indent=2))
    finally:
        orchestrator.close()
    return 0


def probe_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe configured sensors safely")
    parser.add_argument("--config", required=True)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    config = load_config(args.config)
    orchestrator = build_orchestrator(config)
    results: dict[str, object] = {}
    try:
        orchestrator.start()
        for name, driver in orchestrator.drivers.items():
            try:
                results[name] = {
                    "connected": True,
                    "sample": _sample_summary(driver.read()),
                    "health": driver.health().to_dict(),
                }
            except Exception as exc:
                results[name] = {
                    "connected": False,
                    "error_type": type(exc).__name__,
                    "health": driver.health().to_dict(),
                }
    finally:
        orchestrator.close()
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


def collect_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect an offline sensor session")
    parser.add_argument("--config", required=True)
    parser.add_argument("--room", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--participant-range")
    parser.add_argument("--notes", default="")
    parser.add_argument(
        "--known-anomaly",
        action="append",
        default=[],
        help="Known non-personal anomaly; repeat the option for multiple entries",
    )
    parser.add_argument("--realtime", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    if args.duration <= 0:
        parser.error("--duration must be positive")
    config = _with_overrides(
        load_config(args.config),
        room_id=args.room,
        scenario=args.scenario,
    )
    clock = SystemClock() if args.realtime else ManualClock()
    writer = SessionWriter(
        config=config,
        scenario=args.scenario,
        participant_range=args.participant_range,
        notes=args.notes,
        known_anomalies=args.known_anomaly,
        now=clock.now_utc(),
    )
    orchestrator = build_orchestrator(config, clock=clock)
    window_count = math.ceil(args.duration / config.window_seconds)
    try:
        for _ in range(window_count):
            writer.append(orchestrator.run_window())
    finally:
        orchestrator.close()
    path = writer.finalize(clock.now_utc())
    enforce_session_retention(
        config.storage.data_dir,
        max_sessions=config.storage.max_sessions,
        max_age_days=config.storage.retention_days,
    )
    print(
        json.dumps(
            {
                "session_id": writer.session_id,
                "path": str(path),
                "window_count": writer.window_count,
                "raw_audio_persisted": False,
            },
            indent=2,
        )
    )
    return 0


def verify_main(argv: Sequence[str] | None = None) -> int:
    from .session_validation import validate_session

    parser = argparse.ArgumentParser(
        description="Validate an offline session without modifying it"
    )
    parser.add_argument("session_path")
    parser.add_argument("--schema")
    args = parser.parse_args(argv)
    report = validate_session(args.session_path, schema_path=args.schema)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.valid else 1
