from __future__ import annotations

import argparse
import json
from pathlib import Path

from study_space_ml.data.io import read_json
from study_space_ml.inference.post import post_observation


def _load_payloads(path: str) -> list[dict]:
    value = Path(path).expanduser().resolve()
    if value.suffix == ".jsonl":
        rows = []
        with value.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    rows.append(json.loads(line))
        return rows
    return [read_json(value)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="POST EdgeObservation JSON/JSONL to the backend.")
    parser.add_argument("input", help="EdgeObservation JSON or JSONL")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="backend base URL")
    parser.add_argument("--token", help="optional edge API token; defaults to EDGE_API_TOKEN env var")
    args = parser.parse_args(argv)
    payloads = _load_payloads(args.input)
    accepted = []
    for payload in payloads:
        response = post_observation(payload, base_url=args.url, token=args.token)
        accepted.append(response)
        print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
