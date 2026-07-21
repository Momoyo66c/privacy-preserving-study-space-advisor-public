"""Validated streaming reader for Module 1 offline sessions.

Module 2 can depend on this small boundary instead of duplicating checksum,
privacy, JSON Schema, and NPZ path handling.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping

import numpy as np

from .session_validation import SessionValidationReport, validate_session


class InvalidSessionError(ValueError):
    """Raised before any window is exposed from an invalid session package."""

    def __init__(self, report: SessionValidationReport) -> None:
        self.report = report
        summary = "; ".join(report.errors[:3]) or "unknown validation failure"
        super().__init__(f"offline session validation failed: {summary}")


@dataclass(frozen=True, slots=True)
class SessionWindow:
    """One shared-contract payload and its optional local thermal matrix."""

    payload: Mapping[str, Any]
    thermal_frames: np.ndarray | None


class SessionReader:
    """Validate once, then stream windows and thermal NPZ data in file order."""

    def __init__(
        self,
        session_path: str | Path,
        *,
        schema_path: str | Path | None = None,
    ) -> None:
        report = validate_session(session_path, schema_path=schema_path)
        if not report.valid:
            raise InvalidSessionError(report)
        self.path = Path(report.session_path)
        self.session_id = str(report.session_id)
        self._metadata = json.loads(
            (self.path / "session.json").read_text(encoding="utf-8")
        )
        self._payloads = tuple(
            json.loads(line)
            for line in (self.path / "windows.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )

    @property
    def metadata(self) -> dict[str, Any]:
        """Return an isolated metadata copy for feature/training provenance."""

        return deepcopy(self._metadata)

    def __len__(self) -> int:
        return len(self._payloads)

    def __iter__(self) -> Iterator[SessionWindow]:
        return self.iter_windows()

    def iter_windows(self) -> Iterator[SessionWindow]:
        """Yield windows without loading the complete thermal session into RAM."""

        prefix = f"local://{self.session_id}/"
        for stored_payload in self._payloads:
            payload = deepcopy(stored_payload)
            reference = payload["thermal"].get("frames_ref")
            thermal_frames: np.ndarray | None = None
            if reference is not None:
                relative = PurePosixPath(reference.removeprefix(prefix))
                thermal_path = self.path.joinpath(*relative.parts)
                with np.load(thermal_path, allow_pickle=False) as data:
                    thermal_frames = np.asarray(data["frames"], dtype=np.float32).copy()
                thermal_frames.setflags(write=False)
            yield SessionWindow(
                payload=payload,
                thermal_frames=thermal_frames,
            )
