from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from study_space_ml.paths import resolve_windows_path


def read_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    windows_path = resolve_windows_path(path)
    with windows_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {windows_path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"expected JSON object at {windows_path}:{line_number}")
            yield value


def load_windows(path: str | Path) -> list[dict[str, Any]]:
    value = Path(path).expanduser().resolve()
    if value.is_dir() or value.name.endswith(".jsonl"):
        return list(iter_jsonl(value))
    return [read_json(value)]


def write_json(path: str | Path, value: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
