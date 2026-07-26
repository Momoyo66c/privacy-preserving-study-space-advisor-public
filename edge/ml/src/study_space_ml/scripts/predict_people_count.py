from __future__ import annotations

import argparse
import json

from study_space_ml.predictor import PeopleCountPredictor


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict people count for one SensorWindow, windows.jsonl, or session directory.")
    parser.add_argument("input_path", help="A .json SensorWindow, .jsonl windows file, or session directory.")
    parser.add_argument("--artifact", default="artifacts/people_count_rf_real_v0_1", help="Model artifact directory.")
    parser.add_argument("--out", required=True, help="Output .json or .jsonl path.")
    parser.add_argument("--include-features", action="store_true", help="Include full model feature vector in output.")
    args = parser.parse_args()

    predictor = PeopleCountPredictor(args.artifact)
    records = predictor.predict_path(args.input_path, out_path=args.out, include_features=args.include_features)
    print(json.dumps({"prediction_count": len(records), "out": args.out}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
