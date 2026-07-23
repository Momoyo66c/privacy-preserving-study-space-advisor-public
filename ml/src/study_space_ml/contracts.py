from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

CONTRACT_DIR = Path("shared") / "contracts"


def find_repo_root(start: Path | None = None) -> Path:
    """Find the repository root by looking for shared/contracts.

    Scripts may be executed from the repo root, from edge/ml, or through an
    installed console entry point. This keeps schema validation independent
    of the current working directory.
    """
    candidates: list[Path] = []
    if start is not None:
        candidates.append(start.resolve())
    candidates.append(Path.cwd().resolve())
    candidates.extend(Path(__file__).resolve().parents)
    for candidate in candidates:
        for parent in [candidate, *candidate.parents]:
            if (parent / CONTRACT_DIR).is_dir():
                return parent
    raise FileNotFoundError("Could not find repository root containing shared/contracts")


def load_schema(schema_name: str, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    path = root / CONTRACT_DIR / schema_name
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_payload(payload: dict[str, Any], schema_name: str, repo_root: Path | None = None) -> None:
    schema = load_schema(schema_name, repo_root=repo_root)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
