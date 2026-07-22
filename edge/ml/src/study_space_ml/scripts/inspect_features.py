from __future__ import annotations

import argparse
import json
from pathlib import Path

from study_space_ml.data.io import load_windows, write_jsonl
from study_space_ml.features import extract_feature_bundle
from study_space_ml.paths import infer_session_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract feature rows from SensorWindow input.")
    parser.add_argument("input", help="sensor_window.json, windows.jsonl, or session directory")
    parser.add_argument("--out", help="optional JSONL feature output path")
    args = parser.parse_args(argv)
    session_dir = infer_session_dir(args.input)
    rows = []
    for window in load_windows(args.input):
        bundle = extract_feature_bundle(window, session_dir=session_dir)
        rows.append({
            "window_id": window.get("window_id"),
            "room_id": window.get("room_id"),
            "features": bundle.features,
            "summary": bundle.summary,
            "warnings": bundle.warnings,
        })
    if args.out:
        write_jsonl(args.out, rows)
    for row in rows:
        print(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
