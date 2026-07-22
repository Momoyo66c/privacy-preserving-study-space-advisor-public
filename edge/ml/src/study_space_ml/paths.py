from __future__ import annotations

from pathlib import Path


def find_repo_root(start: str | Path | None = None) -> Path:
    """Find the repository root by looking for shared contracts."""
    current = Path(start or Path.cwd()).resolve()
    candidates = [current, *current.parents]
    for candidate in candidates:
        if (candidate / "shared" / "contracts" / "sensor_window.schema.json").is_file():
            return candidate
    # When running from edge/ml source without shared in parents, fall back two levels.
    return Path(__file__).resolve().parents[4]


def default_artifact_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "artifacts" / "rule_model_v0_3_0"


def resolve_windows_path(path: str | Path) -> Path:
    value = Path(path).expanduser().resolve()
    if value.is_dir():
        candidate = value / "windows.jsonl"
        if not candidate.is_file():
            raise FileNotFoundError(f"session directory does not contain windows.jsonl: {value}")
        return candidate
    if not value.is_file():
        raise FileNotFoundError(f"input file not found: {value}")
    return value


def infer_session_dir(path: str | Path) -> Path | None:
    value = Path(path).expanduser().resolve()
    if value.is_dir():
        return value
    if value.name == "windows.jsonl":
        return value.parent
    return None


def resolve_local_ref(frames_ref: str | None, *, session_dir: str | Path | None = None) -> Path | None:
    """Resolve local://<session_id>/thermal/file.npz to a path under the session directory."""
    if not frames_ref or not frames_ref.startswith("local://") or session_dir is None:
        return None
    session_path = Path(session_dir).expanduser().resolve()
    # local://session-id/thermal/name.npz -> thermal/name.npz under that session path.
    parts = frames_ref.removeprefix("local://").split("/")
    if len(parts) >= 3 and parts[1] == "thermal":
        candidate = session_path / "thermal" / parts[-1]
        if candidate.is_file():
            return candidate
    # Be permissive for future local://thermal/name.npz forms.
    if len(parts) >= 2 and parts[0] == "thermal":
        candidate = session_path / "thermal" / parts[-1]
        if candidate.is_file():
            return candidate
    return None
