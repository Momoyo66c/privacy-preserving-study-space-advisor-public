from __future__ import annotations

import argparse
import json

from study_space_ml.data.io import load_windows, write_json
from study_space_ml.data.validation import validate_window_collection


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate SensorWindow JSON/JSONL input.")
    parser.add_argument("input", help="sensor_window.json, windows.jsonl, or session directory")
    parser.add_argument("--out", help="optional JSON report path")
    args = parser.parse_args(argv)
    windows = load_windows(args.input)
    report = validate_window_collection(windows)
    if args.out:
        write_json(args.out, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
