from __future__ import annotations

import argparse
import json

from study_space_ml.data.io import load_windows, write_jsonl
from study_space_ml.inference.predictor import EdgePredictor
from study_space_ml.paths import infer_session_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Predict all windows in a JSONL file/session directory.")
    parser.add_argument("input", help="windows.jsonl or session directory")
    parser.add_argument("--artifact", help="artifact directory containing model.json")
    parser.add_argument("--out", required=True, help="output EdgeObservation JSONL path")
    parser.add_argument("--no-strict", action="store_true", help="do not fail on validation errors")
    args = parser.parse_args(argv)
    predictor = EdgePredictor(artifact_dir=args.artifact)
    session_dir = infer_session_dir(args.input)
    rows = [
        predictor.predict_window(window, session_dir=session_dir, strict=not args.no_strict)
        for window in load_windows(args.input)
    ]
    write_jsonl(args.out, rows)
    print(json.dumps({"written": len(rows), "out": args.out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
