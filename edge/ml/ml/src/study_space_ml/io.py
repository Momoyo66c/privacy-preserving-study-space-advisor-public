from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path: str | Path, *, strict: bool = True) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    p = Path(path)
    for line_no, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        raw = line.strip()
        if not raw:
            continue
        try:
            records.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            msg = f"{p}:{line_no}: invalid JSONL line: {exc}"
            if strict:
                raise ValueError(msg) from exc
            errors.append(msg)
    if errors:
        print("\n".join(errors))
    return records


def write_jsonl(records: Iterable[dict[str, Any]], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for item in records:
            f.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")


def find_session_dirs(dataset_root: str | Path) -> list[Path]:
    """Find directories that contain windows.jsonl.

    Accepts any of:
    - data/real_classroom_v1
    - data/real_classroom_v1/session-xxx
    - a broader data directory containing nested session directories
    """
    root = Path(dataset_root)
    if root.is_file():
        raise ValueError(f"Expected a dataset/session directory, got file: {root}")
    if (root / "windows.jsonl").exists():
        return [root]
    sessions = sorted({p.parent for p in root.rglob("windows.jsonl")})
    if not sessions:
        raise FileNotFoundError(f"No windows.jsonl found under {root}")
    return sessions


def load_relative_features(session_dir: str | Path) -> dict[str, dict[str, Any]]:
    p = Path(session_dir) / "relative_features.jsonl"
    if not p.exists():
        return {}
    rows = read_jsonl(p, strict=False)
    return {row.get("window_id"): row for row in rows if row.get("window_id")}


def load_session_metadata(session_dir: str | Path) -> dict[str, Any]:
    p = Path(session_dir) / "session.json"
    if not p.exists():
        return {}
    return read_json(p)


def discover_labels_file(dataset_root: str | Path) -> Path | None:
    root = Path(dataset_root)
    candidates = [
        root / "labels.csv",
        root.parent / "labels.csv",
        Path.cwd() / "data" / "labels.csv",
        Path.cwd() / "labels.csv",
    ]
    for c in candidates:
        if c.exists():
            return c
    found = sorted(root.rglob("labels.csv"))
    return found[0] if found else None
