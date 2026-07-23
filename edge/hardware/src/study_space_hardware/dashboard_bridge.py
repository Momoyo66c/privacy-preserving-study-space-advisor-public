"""Stream privacy-safe ESP32 sensor snapshots to the local dashboard backend."""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import threading
import time
from collections import deque
from collections.abc import Mapping, Sequence
from datetime import timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from .bootstrap import build_orchestrator
from .config import load_config
from .models import (
    THERMAL_HEIGHT,
    THERMAL_PIXELS,
    THERMAL_WIDTH,
    SensorHealth,
    SensorHealthReport,
    SensorSample,
)
from .orchestrator import SensorOrchestrator
from .session_validation import validate_session
from .storage import SessionWriter, create_session_archive, enforce_session_retention


LOGGER = logging.getLogger(__name__)


def normalize_thermal(values: Sequence[float]) -> list[float]:
    """Normalize one 32 x 24 frame after clipping its outer two percent."""

    if len(values) != THERMAL_PIXELS:
        raise ValueError("thermal frame must contain 768 values")
    numbers = [float(value) for value in values]
    if any(not math.isfinite(value) for value in numbers):
        raise ValueError("thermal frame must contain only finite values")
    ordered = sorted(numbers)
    lower = ordered[int((len(ordered) - 1) * 0.02)]
    upper = ordered[int((len(ordered) - 1) * 0.98)]
    span = upper - lower
    if span <= 1e-9:
        return [0.0] * len(numbers)
    return [round(min(1.0, max(0.0, (value - lower) / span)), 6) for value in numbers]


def count_hot_regions(
    values: Sequence[float],
    *,
    threshold: float = 0.72,
    minimum_pixels: int = 2,
) -> int:
    """Count connected relative-hot regions without inferring people."""

    if len(values) != THERMAL_PIXELS:
        raise ValueError("normalized thermal frame must contain 768 values")
    hot = {index for index, value in enumerate(values) if float(value) >= threshold}
    regions = 0
    while hot:
        stack = [hot.pop()]
        size = 0
        while stack:
            index = stack.pop()
            size += 1
            x, y = index % THERMAL_WIDTH, index // THERMAL_WIDTH
            for neighbor in (
                index - 1 if x > 0 else -1,
                index + 1 if x + 1 < THERMAL_WIDTH else -1,
                index - THERMAL_WIDTH if y > 0 else -1,
                index + THERMAL_WIDTH if y + 1 < THERMAL_HEIGHT else -1,
            ):
                if neighbor in hot:
                    hot.remove(neighbor)
                    stack.append(neighbor)
        if size >= minimum_pixels:
            regions += 1
    return regions


def _health_value(
    reports: Mapping[str, SensorHealthReport],
    name: str,
) -> str:
    report = reports.get(name)
    return (report.status if report else SensorHealth.NOT_CONFIGURED).value


def _environment_health(light: str, climate: str) -> str:
    statuses = {light, climate}
    if statuses == {SensorHealth.OK.value}:
        return SensorHealth.OK.value
    if SensorHealth.OFFLINE.value in statuses:
        return SensorHealth.OFFLINE.value
    if statuses == {SensorHealth.NOT_CONFIGURED.value}:
        return SensorHealth.NOT_CONFIGURED.value
    return SensorHealth.DEGRADED.value


class LiveSnapshotBuilder:
    """Retain the latest samples and build the backend's existing payloads."""

    def __init__(
        self,
        *,
        room_id: str,
        device_id: str,
        expires_in_seconds: int = 5,
        sound_hold_seconds: float = 10.0,
    ) -> None:
        if not 1 <= expires_in_seconds <= 30:
            raise ValueError("expires_in_seconds must be between 1 and 30")
        if sound_hold_seconds <= 0:
            raise ValueError("sound_hold_seconds must be positive")
        self.room_id = room_id
        self.device_id = device_id
        self.expires_in_seconds = expires_in_seconds
        self.sound_hold_seconds = sound_hold_seconds
        self._latest: dict[str, SensorSample] = {}
        self._sound_peaks: deque[tuple[float, float]] = deque()

    def accept(self, sample: SensorSample) -> None:
        if sample.valid:
            self._latest[sample.sensor] = sample
            if sample.sensor == "sound":
                captured_s = sample.captured_at.timestamp()
                self._sound_peaks.append(
                    (
                        captured_s,
                        float(
                            sample.values.get(
                                "relative_level",
                                sample.values.get("peak", 0.0),
                            )
                        ),
                    )
                )
                self._prune_sound_peaks(captured_s)

    def _prune_sound_peaks(self, captured_s: float) -> None:
        cutoff = captured_s - self.sound_hold_seconds
        while self._sound_peaks and self._sound_peaks[0][0] < cutoff:
            self._sound_peaks.popleft()

    def build(self, reports: Mapping[str, SensorHealthReport]) -> dict[str, Any]:
        thermal = self._latest.get("thermal")
        if not self._latest:
            raise RuntimeError("at least one sensor sample is required before publishing")
        thermal_report = reports.get("thermal")
        if thermal_report is not None and thermal_report.status == SensorHealth.OFFLINE:
            thermal = None
        normalized: list[float] | None = None
        if thermal is not None:
            raw_thermal = tuple(
                float(value) for value in thermal.values["temperatures_c"]
            )
            normalized = normalize_thermal(raw_thermal)
        reference_sample = max(
            self._latest.values(),
            key=lambda sample: sample.captured_at,
        )
        self._prune_sound_peaks(reference_sample.captured_at.timestamp())
        sound_health = _health_value(reports, "sound")
        sound = (
            self._latest.get("sound")
            if sound_health == SensorHealth.OK.value
            else None
        )
        sound_peak_max = (
            max((peak for _, peak in self._sound_peaks), default=None)
            if sound is not None
            else None
        )
        light = self._latest.get("light")
        climate = self._latest.get("climate")
        warnings = {
            warning
            for sample in self._latest.values()
            for warning in sample.warnings
            if warning
        }
        if light is not None:
            warning = light.values.get("warning")
            if isinstance(warning, str) and warning:
                warnings.add(warning)
        observed_at = (
            reference_sample.captured_at.astimezone(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
        light_lux = light.values.get("light_lux") if light else None
        light_calibrated = bool(light and light.values.get("calibrated_lux"))
        preview = None
        if thermal is not None and normalized is not None:
            thermal_captured_at = (
                thermal.captured_at.astimezone(timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            )
            preview = {
                "schema_version": "1.0",
                "room_id": self.room_id,
                "captured_at": thermal_captured_at,
                "width": THERMAL_WIDTH,
                "height": THERMAL_HEIGHT,
                "values": normalized,
                "normalization": "window_min_max_clipped",
                "expires_in_seconds": self.expires_in_seconds,
            }
        sound_preview = None
        if sound is not None:
            sound_captured_at = (
                sound.captured_at.astimezone(timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            )
            sound_preview = {
                "schema_version": "1.0",
                "room_id": self.room_id,
                "captured_at": sound_captured_at,
                "rms": float(sound.values["rms"]),
                "expires_in_seconds": min(3, self.expires_in_seconds),
            }
        health = {
            "thermal": _health_value(reports, "thermal"),
            "sound": sound_health,
            "light": _health_value(reports, "light"),
            "climate": _health_value(reports, "climate"),
            "radar": _health_value(reports, "radar"),
        }
        warnings.add("DASHBOARD_ONLY_NO_MODULE2_INFERENCE")
        observation = {
            "schema_version": "1.0",
            "observation_id": f"{self.device_id}-{observed_at}",
            "room_id": self.room_id,
            "device_id": self.device_id,
            "observed_at": observed_at,
            "window_seconds": 5,
            "room_state": "unknown",
            "occupancy_level": "unknown",
            "suitability_score": 0,
            "confidence": 0.0,
            "features": {
                "thermal_hot_region_count": (
                    count_hot_regions(normalized) if normalized is not None else None
                ),
                "radar_active_target_count": None,
                "sound_rms_mean": sound.values.get("rms") if sound else None,
                "sound_peak_max": sound_peak_max,
                "light_relative_mean": light.values.get("light_normalized") if light else None,
                "light_lux": light_lux if light_calibrated else None,
                "temperature_c": climate.values.get("temperature_c") if climate else None,
                "humidity_pct": climate.values.get("humidity_pct") if climate else None,
            },
            "sensor_health": {
                "thermal": health["thermal"],
                "radar": health["radar"],
                "sound": health["sound"],
                "environment": _environment_health(health["light"], health["climate"]),
            },
            "model": {
                "name": "sensor-dashboard-bridge",
                "version": "1.0.0",
                "feature_schema_version": "1.0",
            },
            "warnings": sorted(warnings),
        }
        return {
            "thermal_preview": preview,
            "sound_preview": sound_preview,
            "observation": observation,
        }


class DashboardClient:
    def __init__(
        self,
        *,
        backend_url: str,
        room_id: str,
        edge_token: str | None = None,
        timeout_s: float = 1.5,
    ) -> None:
        parsed = urlsplit(backend_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("backend_url must be an absolute HTTP(S) URL")
        base_url = backend_url.rstrip("/")
        self.preview_url = (
            base_url
            + "/api/v1/edge/rooms/"
            + quote(room_id, safe="")
            + "/thermal-preview"
        )
        self.sound_preview_url = (
            base_url
            + "/api/v1/edge/rooms/"
            + quote(room_id, safe="")
            + "/sound-preview"
        )
        self.observation_url = base_url + "/api/v1/edge/observations"
        self.edge_token = edge_token
        self.timeout_s = timeout_s

    def publish_preview(self, payload: Mapping[str, Any]) -> None:
        self._publish(self.preview_url, "PUT", payload)

    def publish_sound_preview(self, payload: Mapping[str, Any]) -> None:
        self._publish(self.sound_preview_url, "PUT", payload)

    def publish_observation(self, payload: Mapping[str, Any]) -> None:
        self._publish(self.observation_url, "POST", payload)

    def _publish(self, url: str, method: str, payload: Mapping[str, Any]) -> None:
        body = json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.edge_token:
            headers["Authorization"] = f"Bearer {self.edge_token}"
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_s) as response:
                if response.status != 200:
                    raise RuntimeError(f"dashboard backend returned HTTP {response.status}")
        except HTTPError as exc:
            raise RuntimeError(f"dashboard backend returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError("dashboard backend is unreachable") from exc


class LatestSnapshotPublisher:
    """Publish previews continuously and observation summaries every five seconds."""

    def __init__(
        self,
        client: DashboardClient,
        *,
        observation_interval_s: float = 5.0,
    ) -> None:
        if observation_interval_s <= 0:
            raise ValueError("observation_interval_s must be positive")
        self.client = client
        self.observation_interval_s = observation_interval_s
        self._condition = threading.Condition()
        self._latest: Mapping[str, Any] | None = None
        self._stopping = False
        self._thread = threading.Thread(
            target=self._run,
            name="dashboard-publisher",
            daemon=True,
        )
        self.previews_published = 0
        self.sound_previews_published = 0
        self.observations_published = 0
        self.failed = 0
        self._last_observation_at: float | None = None
        self._last_thermal_captured_at: str | None = None
        self._last_sound_captured_at: str | None = None

    def start(self) -> None:
        self._thread.start()

    def submit(self, payload: Mapping[str, Any]) -> None:
        with self._condition:
            self._latest = payload
            self._condition.notify()

    def close(self) -> None:
        with self._condition:
            self._stopping = True
            self._condition.notify()
        self._thread.join(timeout=3.0)

    def _run(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(
                    lambda: self._latest is not None or self._stopping
                )
                payload = self._latest
                self._latest = None
                stopping = self._stopping
            if payload is not None:
                try:
                    preview = payload.get("thermal_preview")
                    if (
                        preview is not None
                        and preview["captured_at"] != self._last_thermal_captured_at
                    ):
                        self.client.publish_preview(preview)
                        self.previews_published += 1
                        self._last_thermal_captured_at = preview["captured_at"]
                    sound_preview = payload.get("sound_preview")
                    if (
                        sound_preview is not None
                        and sound_preview["captured_at"] != self._last_sound_captured_at
                    ):
                        self.client.publish_sound_preview(sound_preview)
                        self.sound_previews_published += 1
                        self._last_sound_captured_at = sound_preview["captured_at"]
                    now = time.monotonic()
                    if (
                        self._last_observation_at is None
                        or now - self._last_observation_at >= self.observation_interval_s
                    ):
                        self.client.publish_observation(payload["observation"])
                        self.observations_published += 1
                        self._last_observation_at = now
                except Exception as exc:
                    self.failed += 1
                    LOGGER.warning(
                        "dashboard_publish_failed error_type=%s",
                        type(exc).__name__,
                    )
            if stopping and self._latest is None:
                return


class SensorDashboardBridge:
    def __init__(
        self,
        *,
        orchestrator: SensorOrchestrator,
        builder: LiveSnapshotBuilder,
        publisher: LatestSnapshotPublisher,
    ) -> None:
        if "thermal" not in orchestrator.drivers:
            raise ValueError("thermal sensor must be enabled for dashboard streaming")
        self.orchestrator = orchestrator
        self.builder = builder
        self.publisher = publisher

    def _observe_sample(self, sample: SensorSample) -> None:
        self.builder.accept(sample)
        if sample.sensor in {"thermal", "sound"}:
            self.publisher.submit(self.builder.build(self.orchestrator.health()))

    def run(
        self,
        *,
        writer: SessionWriter | None = None,
        window_count: int | None = None,
    ) -> int:
        if window_count is not None and window_count < 1:
            raise ValueError("window_count must be positive")
        self.publisher.start()
        completed = 0
        try:
            while window_count is None or completed < window_count:
                window = self.orchestrator.run_window(
                    on_sample=self._observe_sample,
                )
                self.publisher.submit(
                    self.builder.build(self.orchestrator.health())
                )
                if writer is not None:
                    writer.append(window)
                completed += 1
                LOGGER.info(
                    "dashboard_window_complete windows=%d previews=%d observations=%d failed=%d completeness=%.6f",
                    completed,
                    self.publisher.previews_published,
                    self.publisher.observations_published,
                    self.publisher.failed,
                    window.payload["quality"]["completeness"],
                )
        finally:
            self.orchestrator.close()
            self.publisher.close()
        return completed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stream real sensors to the existing dashboard backend endpoints"
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--backend-url", required=True)
    parser.add_argument(
        "--duration",
        type=float,
        help="Collect and package this many seconds while streaming; omit to stream continuously",
    )
    parser.add_argument("--scenario", default="unlabeled_relative_training")
    parser.add_argument("--participant-range")
    parser.add_argument(
        "--notes",
        default=(
            "relative light and sound summaries; source is recorded in session "
            "metadata; no lux or dBA calibration"
        ),
    )
    parser.add_argument("--known-anomaly", action="append", default=[])
    parser.add_argument(
        "--edge-token-env",
        default="EDGE_API_TOKEN",
        help="Environment variable containing the optional bearer token",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    if args.duration is not None and args.duration <= 0:
        parser.error("--duration must be positive")
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s level=%(levelname)s logger=%(name)s message=%(message)s",
    )
    config = load_config(args.config)
    orchestrator = build_orchestrator(config)
    client = DashboardClient(
        backend_url=args.backend_url,
        room_id=config.room_id,
        edge_token=os.environ.get(args.edge_token_env) or None,
    )
    bridge = SensorDashboardBridge(
        orchestrator=orchestrator,
        builder=LiveSnapshotBuilder(room_id=config.room_id, device_id=config.device_id),
        publisher=LatestSnapshotPublisher(
            client,
            observation_interval_s=config.window_seconds,
        ),
    )
    writer = (
        SessionWriter(
            config=config,
            scenario=args.scenario,
            participant_range=args.participant_range,
            notes=args.notes,
            known_anomalies=args.known_anomaly,
        )
        if args.duration is not None
        else None
    )
    interrupted = False
    try:
        bridge.run(
            writer=writer,
            window_count=(
                math.ceil(args.duration / config.window_seconds)
                if args.duration is not None
                else None
            ),
        )
    except KeyboardInterrupt:
        interrupted = True
        LOGGER.info("dashboard_bridge_stopped")
    if writer is None:
        return 0
    session_path = writer.finalize()
    report = validate_session(session_path)
    archive_path = None
    archive_sha256 = None
    if report.valid:
        archive_path, archive_sha256 = create_session_archive(session_path)
    enforce_session_retention(
        config.storage.data_dir,
        max_sessions=config.storage.max_sessions,
        max_age_days=config.storage.retention_days,
    )
    print(
        json.dumps(
            {
                "session_id": writer.session_id,
                "session_path": str(session_path),
                "window_count": writer.window_count,
                "validation": report.to_dict(),
                "archive_path": str(archive_path) if archive_path else None,
                "archive_sha256": archive_sha256,
                "interrupted": interrupted,
                "raw_audio_persisted": False,
                "light_lux_calibrated": False,
                "sound_db_calibrated": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report.valid and writer.window_count > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
