from __future__ import annotations

import argparse
import json
from pathlib import Path

from .client import post_observation
from .contracts import validate_payload
from .jsonl import load_labels_csv, read_windows_jsonl, resolve_windows_jsonl, write_jsonl
from .predictor import EdgePredictor


def _read_json(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return value


def _write_json(path: str | Path, payload: dict) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def predict_window_main() -> None:
    parser = argparse.ArgumentParser(description="Predict one SensorWindow JSON file and write one EdgeObservation JSON file.")
    parser.add_argument("window_json", help="Path to one SensorWindow JSON file")
    parser.add_argument("--out", required=True, help="Output EdgeObservation JSON path")
    parser.add_argument("--model", default=None, help="Optional model.json path")
    parser.add_argument("--no-contract-validation", action="store_true", help="Skip JSON Schema validation")
    args = parser.parse_args()

    predictor = EdgePredictor(args.model, validate_contracts=not args.no_contract_validation)
    observation = predictor.predict_window(_read_json(args.window_json))
    _write_json(args.out, observation)
    print(f"wrote {args.out}")


def predict_jsonl_main() -> None:
    parser = argparse.ArgumentParser(description="Predict windows.jsonl or a session directory and write EdgeObservation JSONL.")
    parser.add_argument("windows", help="Path to windows.jsonl or a session directory containing windows.jsonl")
    parser.add_argument("--out", required=True, help="Output EdgeObservation JSONL path")
    parser.add_argument("--model", default=None, help="Optional model.json path")
    parser.add_argument("--no-contract-validation", action="store_true", help="Skip JSON Schema validation")
    args = parser.parse_args()

    predictor = EdgePredictor(args.model, validate_contracts=not args.no_contract_validation)
    records = [predictor.predict_window(window) for window in read_windows_jsonl(args.windows)]
    write_jsonl(args.out, records)
    print(f"wrote {len(records)} observations to {args.out}")


def post_observation_main() -> None:
    parser = argparse.ArgumentParser(description="Post EdgeObservation JSON or JSONL to the backend.")
    parser.add_argument("observations", help="Path to EdgeObservation JSON or JSONL")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Backend base URL or full observations endpoint")
    parser.add_argument("--token", default=None, help="Bearer token; defaults to EDGE_API_TOKEN env var")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout seconds")
    args = parser.parse_args()

    path = Path(args.observations)
    sent = 0
    if path.suffix.lower() == ".jsonl":
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                response = post_observation(json.loads(line), base_url=args.url, token=args.token, timeout=args.timeout)
                print(json.dumps(response, ensure_ascii=False))
                sent += 1
    else:
        response = post_observation(_read_json(path), base_url=args.url, token=args.token, timeout=args.timeout)
        print(json.dumps(response, ensure_ascii=False))
        sent = 1
    print(f"posted {sent} observation(s)")


def validate_dataset_main() -> None:
    parser = argparse.ArgumentParser(description="Validate Module 1 sessions and a separate labels.csv before future training.")
    parser.add_argument("sessions", help="Path to data/sessions or one session directory")
    parser.add_argument("--labels", required=True, help="Path to labels.csv")
    args = parser.parse_args()

    labels = load_labels_csv(args.labels)
    sessions_root = Path(args.sessions)
    if (sessions_root / "windows.jsonl").is_file():
        session_paths = [sessions_root]
    else:
        session_paths = sorted(path for path in sessions_root.iterdir() if (path / "windows.jsonl").is_file())
    if not session_paths:
        raise FileNotFoundError(f"No session windows.jsonl files found under {sessions_root}")

    window_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    validated = 0
    for session_path in session_paths:
        for window in read_windows_jsonl(resolve_windows_jsonl(session_path)):
            validate_payload(window, "sensor_window.schema.json")
            window_id = str(window.get("window_id"))
            if window_id in window_ids:
                duplicate_ids.add(window_id)
            window_ids.add(window_id)
            validated += 1
    missing_windows = sorted(set(labels) - window_ids)
    unlabeled_windows = sorted(window_ids - set(labels))
    report = {
        "session_count": len(session_paths),
        "window_count": validated,
        "label_count": len(labels),
        "duplicate_window_ids": sorted(duplicate_ids),
        "labels_without_windows": missing_windows,
        "windows_without_labels": unlabeled_windows,
        "ok_for_training": not duplicate_ids and not missing_windows,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if duplicate_ids or missing_windows:
        raise SystemExit(1)
