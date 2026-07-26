from __future__ import annotations

import argparse
import json

from study_space_ml.train import train_people_count_model


def main() -> None:
    parser = argparse.ArgumentParser(description="Train RandomForest people-count model.")
    parser.add_argument("dataset_root", help="Dataset root containing session-* folders.")
    parser.add_argument("--labels", default=None, help="Optional labels.csv path. Defaults to dataset_root/labels.csv.")
    parser.add_argument("--out-dir", default="artifacts/people_count_rf_custom", help="Artifact output directory.")
    parser.add_argument("--random-state", type=int, default=42)
    args = parser.parse_args()

    meta = train_people_count_model(
        args.dataset_root,
        labels_path=args.labels,
        out_dir=args.out_dir,
        random_state=args.random_state,
    )
    print(json.dumps({
        "artifact_dir": args.out_dir,
        "training_rows": meta["training_rows"],
        "session_count": meta["session_count"],
        "holdout_metrics": meta["holdout_evaluation"].get("metrics"),
        "leave_one_group_out": meta["leave_one_group_out_evaluation"].get("overall_metrics"),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
