from __future__ import annotations

import argparse
import json
from pathlib import Path

from study_space_ml.data.io import read_json, write_json
from study_space_ml.inference.predictor import EdgePredictor
from study_space_ml.paths import infer_session_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Predict one SensorWindow and write an EdgeObservation.")
    parser.add_argument("input", help="sensor_window.json")
    parser.add_argument("--artifact", help="artifact directory containing model.json")
    parser.add_argument("--session-dir", help="session directory for resolving local thermal NPZ refs")
    parser.add_argument("--out", help="output JSON path")
    parser.add_argument("--no-strict", action="store_true", help="do not fail on validation errors")
    args = parser.parse_args(argv)
    window = read_json(args.input)
    predictor = EdgePredictor(artifact_dir=args.artifact)
    session_dir = args.session_dir or infer_session_dir(args.input)
    payload = predictor.predict_window(window, session_dir=session_dir, strict=not args.no_strict)
    if args.out:
        write_json(args.out, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
