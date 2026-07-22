from __future__ import annotations

import argparse
import json

from study_space_ml.training.train_rule import train_rule_model


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recalibrate the deterministic rule baseline from labels.csv.")
    parser.add_argument("--windows", required=True, help="windows.jsonl or session directory")
    parser.add_argument("--labels", required=True, help="labels.csv")
    parser.add_argument("--out", required=True, help="artifact output directory")
    args = parser.parse_args(argv)
    report = train_rule_model(windows_path=args.windows, labels_path=args.labels, out_dir=args.out)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
