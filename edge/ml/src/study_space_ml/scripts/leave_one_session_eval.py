from __future__ import annotations

import argparse
import json

from study_space_ml.evaluation import evaluate_leave_one_session


def main() -> None:
    parser = argparse.ArgumentParser(description="Run leave-one-session-out evaluation for people-count model.")
    parser.add_argument("dataset_root", help="Dataset root containing session-* folders.")
    parser.add_argument("--labels", default=None, help="Optional labels.csv path. Defaults to dataset_root/labels.csv when discoverable.")
    parser.add_argument("--out-dir", default="outputs/leave_one_session", help="Evaluation output directory.")
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--save-fold-models", action="store_true", help="Save one model per held-out session fold.")
    args = parser.parse_args()

    summary = evaluate_leave_one_session(
        args.dataset_root,
        labels_path=args.labels,
        out_dir=args.out_dir,
        random_state=args.random_state,
        save_fold_models=args.save_fold_models,
    )
    print(json.dumps({
        "out_dir": args.out_dir,
        "session_count": summary["session_count"],
        "window_count": summary["window_count"],
        "overall_metrics": summary["overall_metrics"],
    }, indent=2, ensure_ascii=False, allow_nan=True))


if __name__ == "__main__":
    main()
