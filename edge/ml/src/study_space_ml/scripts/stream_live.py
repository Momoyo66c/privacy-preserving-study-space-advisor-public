from __future__ import annotations

import argparse
import logging
import math
import os
from collections.abc import Sequence
from pathlib import Path

from study_space_hardware.bootstrap import build_orchestrator
from study_space_hardware.config import load_config
from study_space_hardware.dashboard_bridge import (
    DashboardClient,
    LatestSnapshotPublisher,
    LiveSnapshotBuilder,
    SensorDashboardBridge,
)

from study_space_ml.live_inference import LiveInferenceProcessor
from study_space_ml.predictor import PeopleCountPredictor


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run Module 1 acquisition plus Module 2 people count/state fusion "
            "and publish privacy-safe live summaries"
        )
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--backend-url", required=True)
    parser.add_argument("--people-count-artifact", required=True)
    parser.add_argument(
        "--thermal-count-calibration-profile",
        default=str(Path("~/.config/pssa/thermal-count-calibration.json")),
        help="Aggregate zero-to-four thermal count calibration profile",
    )
    parser.add_argument(
        "--thermal-count-calibration-command",
        default="/tmp/pssa-thermal-count-calibration.json",
        help="One-shot local calibration command JSON",
    )
    parser.add_argument(
        "--duration",
        type=float,
        help="Optional run duration in seconds; omit to stream continuously",
    )
    parser.add_argument("--edge-token-env", default="EDGE_API_TOKEN")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    if args.duration is not None and args.duration <= 0:
        parser.error("--duration must be positive")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s level=%(levelname)s logger=%(name)s message=%(message)s",
    )
    config = load_config(args.config)
    orchestrator = build_orchestrator(config)
    client = DashboardClient(
        backend_url=args.backend_url,
        room_id=config.room_id,
        edge_token=os.environ.get(args.edge_token_env) or None,
    )
    bridge = SensorDashboardBridge(
        orchestrator=orchestrator,
        builder=LiveSnapshotBuilder(
            room_id=config.room_id,
            device_id=config.device_id,
        ),
        publisher=LatestSnapshotPublisher(
            client,
            observation_interval_s=config.window_seconds,
        ),
        window_processor=LiveInferenceProcessor(
            PeopleCountPredictor(args.people_count_artifact),
            thermal_calibration_profile_path=args.thermal_count_calibration_profile,
            thermal_calibration_command_path=args.thermal_count_calibration_command,
        ),
    )
    try:
        bridge.run(
            window_count=(
                math.ceil(args.duration / config.window_seconds)
                if args.duration is not None
                else None
            )
        )
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("module2_live_stream_stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
