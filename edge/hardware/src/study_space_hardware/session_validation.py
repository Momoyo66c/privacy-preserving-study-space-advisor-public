"""Offline-session integrity, contract, and privacy validation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
from jsonschema import Draft202012Validator, FormatChecker


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_PROHIBITED_SUFFIXES = {
    ".aac",
    ".avi",
    ".bmp",
    ".flac",
    ".gif",
    ".jpeg",
    ".jpg",
    ".m4a",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".ogg",
    ".pcm",
    ".png",
    ".wav",
}
_PRIVACY_FALSE_FIELDS = (
    "names_recorded",
    "student_ids_recorded",
    "raw_audio_persisted",
    "rgb_images_recorded",
)


@dataclass(frozen=True, slots=True)
class SessionValidationReport:
    session_path: str
    session_id: str | None
    valid: bool
    window_count: int
    checked_files: int
    thermal_files: int
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_path": self.session_path,
            "session_id": self.session_id,
            "valid": self.valid,
            "window_count": self.window_count,
            "checked_files": self.checked_files,
            "thermal_files": self.thermal_files,
            "errors": list(self.errors),
        }


def default_sensor_window_schema() -> Path:
    """Locate the shared contract in a repository or editable installation."""

    candidate = (
        Path(__file__).resolve().parents[4]
        / "shared/contracts/sensor_window.schema.json"
    )
    if not candidate.is_file():
        raise FileNotFoundError(
            "shared sensor-window schema not found; pass an explicit schema path"
        )
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path, label: str, errors: list[str]) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"missing required file: {label}")
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"invalid {label}: {type(exc).__name__}: {exc}")
    return None


def _safe_relative_path(value: str) -> PurePosixPath | None:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        return None
    return path


def validate_session(
    session_path: str | Path,
    *,
    schema_path: str | Path | None = None,
) -> SessionValidationReport:
    """Validate a collected session without modifying it."""

    root = Path(session_path).expanduser().resolve()
    errors: list[str] = []
    if not root.is_dir():
        return SessionValidationReport(
            session_path=str(root),
            session_id=None,
            valid=False,
            window_count=0,
            checked_files=0,
            thermal_files=0,
            errors=("session path is not a directory",),
        )

    symlinks = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_symlink())
    errors.extend(f"session contains a symbolic link: {path}" for path in symlinks)

    files = sorted(path for path in root.rglob("*") if path.is_file() and not path.is_symlink())
    relative_files = {path.relative_to(root).as_posix(): path for path in files}
    prohibited = sorted(
        name
        for name, path in relative_files.items()
        if path.suffix.lower() in _PROHIBITED_SUFFIXES
    )
    errors.extend(f"prohibited audio/image/video file: {name}" for name in prohibited)

    metadata = _load_json(root / "session.json", "session.json", errors)
    session_id: str | None = None
    declared_window_count: int | None = None
    if isinstance(metadata, dict):
        raw_session_id = metadata.get("session_id")
        if isinstance(raw_session_id, str) and raw_session_id:
            session_id = raw_session_id
            if session_id != root.name:
                errors.append("session_id does not match the session directory name")
        else:
            errors.append("session.json session_id must be a non-empty string")
        raw_count = metadata.get("window_count")
        if isinstance(raw_count, int) and raw_count >= 0:
            declared_window_count = raw_count
        else:
            errors.append("session.json window_count must be a non-negative integer")
        privacy = metadata.get("privacy")
        if not isinstance(privacy, dict):
            errors.append("session.json privacy must be an object")
        else:
            for field in _PRIVACY_FALSE_FIELDS:
                if privacy.get(field) is not False:
                    errors.append(f"session privacy field must be false: {field}")
        anomalies = metadata.get("known_anomalies")
        if not isinstance(anomalies, list) or not all(
            isinstance(item, str) and item.strip() for item in anomalies
        ):
            errors.append("known_anomalies must be an array of non-empty strings")
    elif metadata is not None:
        errors.append("session.json root must be an object")

    checksum_data = _load_json(root / "checksums.json", "checksums.json", errors)
    expected_checksum_files = set(relative_files) - {"checksums.json"}
    if isinstance(checksum_data, dict):
        checksum_names = set(checksum_data)
        for missing in sorted(expected_checksum_files - checksum_names):
            errors.append(f"file missing from checksums.json: {missing}")
        for extra in sorted(checksum_names - expected_checksum_files):
            errors.append(f"checksums.json references missing file: {extra}")
        for name in sorted(checksum_names & expected_checksum_files):
            safe_name = _safe_relative_path(name)
            expected = checksum_data[name]
            if safe_name is None:
                errors.append(f"unsafe checksum path: {name}")
            elif not isinstance(expected, str) or not _SHA256_PATTERN.fullmatch(expected):
                errors.append(f"invalid SHA-256 value for: {name}")
            elif _sha256(relative_files[name]) != expected:
                errors.append(f"checksum mismatch: {name}")
    elif checksum_data is not None:
        errors.append("checksums.json root must be an object")

    try:
        schema_file = Path(schema_path) if schema_path else default_sensor_window_schema()
        schema = json.loads(schema_file.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator: Draft202012Validator | None = Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"unable to load sensor-window schema: {type(exc).__name__}: {exc}")
        validator = None

    windows: list[dict[str, Any]] = []
    windows_path = root / "windows.jsonl"
    try:
        with windows_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    errors.append(f"windows.jsonl line {line_number} is empty")
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(
                        f"windows.jsonl line {line_number} is invalid JSON: {exc}"
                    )
                    continue
                if not isinstance(payload, dict):
                    errors.append(f"windows.jsonl line {line_number} must be an object")
                    continue
                windows.append(payload)
                if validator is not None:
                    schema_errors = sorted(
                        validator.iter_errors(payload),
                        key=lambda item: list(item.absolute_path),
                    )
                    errors.extend(
                        f"windows.jsonl line {line_number} schema error at "
                        f"{'/'.join(map(str, item.absolute_path)) or '<root>'}: "
                        f"{item.message}"
                        for item in schema_errors
                    )
    except FileNotFoundError:
        errors.append("missing required file: windows.jsonl")
    except (OSError, UnicodeError) as exc:
        errors.append(f"invalid windows.jsonl: {type(exc).__name__}: {exc}")

    if declared_window_count is not None and declared_window_count != len(windows):
        errors.append(
            "session.json window_count does not match valid windows.jsonl records"
        )
    window_ids = [payload.get("window_id") for payload in windows]
    if len(window_ids) != len(set(map(str, window_ids))):
        errors.append("windows.jsonl contains duplicate window_id values")

    referenced_thermal: set[str] = set()
    for index, payload in enumerate(windows, start=1):
        thermal = payload.get("thermal")
        if not isinstance(thermal, dict) or "frames_ref" not in thermal:
            continue
        reference = thermal["frames_ref"]
        prefix = f"local://{session_id}/" if session_id else None
        if not isinstance(reference, str) or prefix is None or not reference.startswith(prefix):
            errors.append(f"window {index} has invalid thermal frames_ref")
            continue
        relative_name = reference[len(prefix) :]
        safe_name = _safe_relative_path(relative_name)
        if safe_name is None or not safe_name.parts or safe_name.parts[0] != "thermal":
            errors.append(f"window {index} has unsafe thermal frames_ref")
            continue
        name = safe_name.as_posix()
        referenced_thermal.add(name)
        thermal_path = root / Path(*safe_name.parts)
        if not thermal_path.is_file():
            errors.append(f"window {index} thermal file is missing: {name}")
            continue
        try:
            with np.load(thermal_path, allow_pickle=False) as data:
                if "frames" not in data:
                    errors.append(f"thermal NPZ has no frames array: {name}")
                    continue
                frames = data["frames"]
                expected_frames = thermal.get("frame_count")
                if frames.ndim != 2 or frames.shape[1:] != (768,):
                    errors.append(f"thermal NPZ must have shape (N, 768): {name}")
                elif not isinstance(expected_frames, int) or frames.shape[0] != expected_frames:
                    errors.append(f"thermal NPZ frame count mismatch: {name}")
        except (OSError, ValueError) as exc:
            errors.append(f"invalid thermal NPZ {name}: {type(exc).__name__}: {exc}")

    actual_thermal = {
        name for name in relative_files if name.startswith("thermal/") and name.endswith(".npz")
    }
    for name in sorted(actual_thermal - referenced_thermal):
        errors.append(f"unreferenced thermal NPZ: {name}")

    return SessionValidationReport(
        session_path=str(root),
        session_id=session_id,
        valid=not errors,
        window_count=len(windows),
        checked_files=len(files),
        thermal_files=len(actual_thermal),
        errors=tuple(errors),
    )
