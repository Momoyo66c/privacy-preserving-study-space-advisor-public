from __future__ import annotations

import argparse
from pathlib import Path

from study_space_ml.dataset import build_feature_table, build_training_table


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract people-count model features from SensorWindow sessions.")
    parser.add_argument("dataset_root", help="Dataset root containing session-* folders, or one session directory.")
    parser.add_argument("--labels", default=None, help="Optional labels.csv path. If provided, output includes people_count.")
    parser.add_argument("--out", required=True, help="Output CSV path.")
    args = parser.parse_args()

    if args.labels:
        df = build_training_table(args.dataset_root, labels_path=args.labels)
    else:
        df = build_feature_table(args.dataset_root)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"Wrote {len(df)} rows to {out}")


if __name__ == "__main__":
    main()
