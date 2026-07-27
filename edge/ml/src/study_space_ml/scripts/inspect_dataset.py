from __future__ import annotations

import argparse
import json

from study_space_ml.dataset import summarize_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect real classroom dataset structure.")
    parser.add_argument("dataset_root", help="Dataset root or session directory.")
    args = parser.parse_args()
    print(json.dumps(summarize_dataset(args.dataset_root), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
