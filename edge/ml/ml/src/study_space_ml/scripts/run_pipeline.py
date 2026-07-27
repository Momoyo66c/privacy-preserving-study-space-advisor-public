from __future__ import annotations

import argparse
import json
from pathlib import Path

from study_space_ml.data.io import load_windows, write_jsonl
from study_space_ml.data.validation import validate_window_collection
from study_space_ml.features import extract_feature_bundle
from study_space_ml.inference.post import post_observations
from study_space_ml.inference.predictor import EdgePredictor
from study_space_ml.paths import infer_session_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate input, extract features, predict EdgeObservations, and optionally POST them.")
    parser.add_argument("input", help="sensor_window.json, windows.jsonl, or session directory")
    parser.add_argument("--artifact", help="artifact directory containing model.json")
    parser.add_argument("--features-out", help="optional JSONL feature output")
    parser.add_argument("--observations-out", required=True, help="EdgeObservation JSONL output")
    parser.add_argument("--post-url", help="backend base URL, e.g. http://127.0.0.1:8000")
    parser.add_argument("--token", help="optional backend edge API token")
    parser.add_argument("--no-strict", action="store_true", help="degrade instead of failing on validation errors")
    args = parser.parse_args(argv)

    windows = load_windows(args.input)
    validation_report = validate_window_collection(windows)
    strict = not args.no_strict
    if strict and not validation_report["valid"]:
        print(json.dumps(validation_report, ensure_ascii=False, indent=2))
        return 1

    session_dir = infer_session_dir(args.input)
    feature_rows = []
    predictor = EdgePredictor(artifact_dir=args.artifact)
    observation_rows = []
    for window in windows:
        bundle = extract_feature_bundle(window, session_dir=session_dir)
        feature_rows.append({
            "window_id": window.get("window_id"),
            "room_id": window.get("room_id"),
            "features": bundle.features,
            "summary": bundle.summary,
            "warnings": bundle.warnings,
        })
        observation_rows.append(predictor.predict_window(window, session_dir=session_dir, strict=strict))

    if args.features_out:
        write_jsonl(args.features_out, feature_rows)
    write_jsonl(args.observations_out, observation_rows)

    result = {
        "input_windows": len(windows),
        "validation_valid": validation_report["valid"],
        "features_out": args.features_out,
        "observations_out": args.observations_out,
        "posted": None,
    }
    if args.post_url:
        post_results = post_observations(observation_rows, base_url=args.post_url, token=args.token)
        result["posted"] = post_results
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
