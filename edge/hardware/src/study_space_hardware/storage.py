"""Privacy-safe offline collection sessions and NPZ thermal persistence."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Sequence
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .config import HardwareConfig
from .models import CollectedWindow, format_utc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _session_id(now: datetime) -> str:
    timestamp = format_utc(now, milliseconds=True)
    compact = timestamp.replace("-", "").replace(":", "").replace(".", "")
    return f"session-{compact}-{uuid4().hex[:8]}"


class SessionWriter:
    """Write one offline session without persisting audio or personal identity."""

    def __init__(
        self,
        *,
        config: HardwareConfig,
        scenario: str,
        base_dir: str | Path | None = None,
        participant_range: str | None = None,
        notes: str = "",
        known_anomalies: Sequence[str] | None = None,
        now: datetime | None = None,
    ) -> None:
        started_at = now or datetime.now(timezone.utc)
        self.config = config
        self.scenario = scenario
        self.started_at = started_at
        self.session_id = _session_id(started_at)
        root = Path(base_dir or config.storage.data_dir)
        self.path = root / self.session_id
        self.thermal_dir = self.path / "thermal"
        self.path.mkdir(parents=True, exist_ok=False)
        self.thermal_dir.mkdir()
        self.windows_path = self.path / "windows.jsonl"
        self.session_path = self.path / "session.json"
        self.checksums_path = self.path / "checksums.json"
        self.window_count = 0
        anomaly_values = (
            (known_anomalies,)
            if isinstance(known_anomalies, str)
            else known_anomalies or ()
        )
        normalized_anomalies = [
            str(value).strip()
            for value in anomaly_values
            if str(value).strip()
        ]
        self._metadata: dict[str, Any] = {
            "schema_version": "1.0",
            "session_id": self.session_id,
            "room_id": config.room_id,
            "device_id": config.device_id,
            "scenario": scenario,
            "started_at": format_utc(started_at),
            "ended_at": None,
            "participant_range": participant_range,
            "operator_notes": notes,
            "known_anomalies": normalized_anomalies,
            "privacy": {
                "names_recorded": False,
                "student_ids_recorded": False,
                "raw_audio_persisted": False,
                "rgb_images_recorded": False,
            },
            "driver_version": "privacy-study-space-hardware/0.1.0",
            "sampling_config": {
                "window_seconds": config.window_seconds,
                "sensors": {
                    name: {
                        "enabled": settings.enabled,
                        "sample_rate_hz": settings.sample_rate_hz,
                    }
                    for name, settings in config.sensors.items()
                },
            },
            "window_count": 0,
        }
        self._write_json(self.session_path, self._metadata)

    def append(self, window: CollectedWindow) -> dict[str, Any]:
        payload = deepcopy(window.payload)
        window_id = str(payload["window_id"])
        if window.thermal_frames:
            try:
                import numpy as np
            except ImportError as exc:
                raise RuntimeError(
                    "NumPy is required to store thermal frames as NPZ"
                ) from exc
            thermal_name = f"{window_id}.npz"
            thermal_path = self.thermal_dir / thermal_name
            np.savez_compressed(
                thermal_path,
                frames=np.asarray(window.thermal_frames, dtype=np.float32),
            )
            payload["thermal"]["frames_ref"] = (
                f"local://{self.session_id}/thermal/{thermal_name}"
            )
        with self.windows_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
            handle.write("\n")
        self.window_count += 1
        self._metadata["window_count"] = self.window_count
        self._write_json(self.session_path, self._metadata)
        self._write_checksums()
        return payload

    def finalize(self, ended_at: datetime | None = None) -> Path:
        self._metadata["ended_at"] = format_utc(
            ended_at or datetime.now(timezone.utc)
        )
        self._metadata["window_count"] = self.window_count
        self._write_json(self.session_path, self._metadata)
        self._write_checksums()
        return self.path

    def _write_checksums(self) -> None:
        checksums = {
            str(path.relative_to(self.path)): _sha256(path)
            for path in sorted(self.path.rglob("*"))
            if path.is_file() and path != self.checksums_path
        }
        self._write_json(self.checksums_path, checksums)

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.write_text(
            json.dumps(value, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )


def enforce_session_retention(
    base_dir: str | Path,
    *,
    max_sessions: int,
    max_age_days: int | None = None,
    now: datetime | None = None,
) -> list[Path]:
    """Delete expired/excess session directories, leaving unrelated data alone."""

    if max_sessions < 1:
        raise ValueError("max_sessions must be positive")
    if max_age_days is not None and max_age_days < 1:
        raise ValueError("max_age_days must be positive")
    root = Path(base_dir)
    if not root.exists():
        return []
    sessions = sorted(
        (
            path
            for path in root.iterdir()
            if path.is_dir()
            and path.name.startswith("session-")
            and (path / "session.json").is_file()
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    removed: list[Path] = []
    retained = sessions
    if max_age_days is not None:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        cutoff = current.timestamp() - timedelta(days=max_age_days).total_seconds()
        expired = [path for path in sessions if path.stat().st_mtime < cutoff]
        for path in expired:
            shutil.rmtree(path)
            removed.append(path)
        retained = [path for path in sessions if path not in expired]
    for path in retained[max_sessions:]:
        shutil.rmtree(path)
        removed.append(path)
    return removed
