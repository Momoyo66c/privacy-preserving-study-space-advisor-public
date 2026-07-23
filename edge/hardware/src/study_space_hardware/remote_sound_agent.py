"""Windows microphone agent that transmits summaries, never raw audio."""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import uuid4

from .drivers.remote_sound import REMOTE_SOUND_PATH
from .drivers.sound_level import summarize_audio


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def build_feature_payload(
    chunk: Any,
    *,
    room_id: str,
    device_id: str,
    window_ms: int,
    sample_id: str | None = None,
    captured_at: str | None = None,
) -> dict[str, Any]:
    """Convert one in-memory chunk to the strict privacy-safe payload."""

    if hasattr(chunk, "ravel"):
        flattened = [float(value) for value in chunk.ravel().tolist()]
    elif isinstance(chunk, (list, tuple)):
        flattened = [float(value) for value in chunk]
    else:
        flattened = [float(chunk)]
    try:
        summary = summarize_audio(flattened)
    finally:
        del flattened
        del chunk
    bounded = {
        name: min(1.0, max(0.0, float(summary[name])))
        for name in ("rms", "std", "peak")
    }
    if not all(math.isfinite(value) for value in bounded.values()):
        raise ValueError("microphone summary contains non-finite values")
    return {
        "schema_version": "1.0",
        "sample_id": sample_id or str(uuid4()),
        "device_id": device_id,
        "room_id": room_id,
        "captured_at": captured_at or _utc_now(),
        "window_ms": int(window_ms),
        **bounded,
        "calibrated_db": False,
        "raw_audio_persisted": False,
    }


def post_feature(
    url: str,
    token: str,
    payload: dict[str, Any],
    *,
    timeout_s: float = 4.0,
) -> dict[str, Any]:
    body = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        result = json.loads(response.read())
    if not isinstance(result, dict) or result.get("accepted") is not True:
        raise RuntimeError("remote sound receiver did not accept the summary")
    return result


def summarize_feature_rows(
    rows: Sequence[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    if not rows:
        raise ValueError("at least one feature row is required")

    def metric_summary(name: str) -> dict[str, float]:
        values = sorted(float(row[name]) for row in rows)
        if not all(math.isfinite(value) and 0 <= value <= 1 for value in values):
            raise ValueError("diagnostic features must be finite values from 0 to 1")
        position = (len(values) - 1) * 0.95
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            p95 = values[lower]
        else:
            weight = position - lower
            p95 = values[lower] * (1.0 - weight) + values[upper] * weight
        return {
            "minimum": values[0],
            "median": float(statistics.median(values)),
            "p95": float(p95),
            "maximum": values[-1],
        }

    return {
        name: metric_summary(name)
        for name in ("rms", "std", "peak")
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read short Windows microphone buffers, immediately reduce them to "
            "RMS/std/peak, and send only those summaries through an SSH tunnel."
        )
    )
    parser.add_argument(
        "--url",
        default=f"http://127.0.0.1:18766{REMOTE_SOUND_PATH}",
        help="SSH-forwarded loopback receiver URL",
    )
    parser.add_argument("--room-id", default="room_a")
    parser.add_argument("--device-id", default="windows-laptop-mic")
    parser.add_argument(
        "--token-env",
        default="PSSA_REMOTE_SOUND_TOKEN",
        help="environment variable containing the bearer token",
    )
    parser.add_argument("--sample-rate-hz", type=int, default=16_000)
    parser.add_argument("--window-ms", type=int, default=1_000)
    parser.add_argument(
        "--device",
        default=None,
        help="sounddevice input index or name; default uses the OS input",
    )
    parser.add_argument(
        "--windows",
        type=int,
        default=0,
        help="number of summaries to send; 0 runs until Ctrl-C",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="list audio devices without opening the microphone",
    )
    parser.add_argument(
        "--diagnostic-summary",
        action="store_true",
        help=(
            "print one aggregate summary after a bounded --windows run; "
            "individual feature values are not printed or written"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        import sounddevice
    except ImportError:
        print(
            "sounddevice is required; install the Module 1 hardware extra",
            file=sys.stderr,
        )
        return 2
    if args.list_devices:
        print(sounddevice.query_devices())
        return 0
    if args.sample_rate_hz < 8_000 or args.sample_rate_hz > 48_000:
        print("sample-rate-hz must be between 8000 and 48000", file=sys.stderr)
        return 2
    if args.window_ms < 100 or args.window_ms > 2_000:
        print("window-ms must be between 100 and 2000", file=sys.stderr)
        return 2
    if args.windows < 0:
        print("windows cannot be negative", file=sys.stderr)
        return 2
    if args.diagnostic_summary and args.windows < 3:
        print(
            "--diagnostic-summary requires --windows of at least 3",
            file=sys.stderr,
        )
        return 2
    token = os.environ.get(args.token_env, "")
    if len(token) < 24 or any(char.isspace() for char in token):
        print(
            f"{args.token_env} must contain at least 24 non-space characters",
            file=sys.stderr,
        )
        return 2
    device: int | str | None = args.device
    if isinstance(device, str) and device.isdecimal():
        device = int(device)
    block_frames = round(args.sample_rate_hz * args.window_ms / 1_000)
    sent = 0
    diagnostic_rows: list[dict[str, Any]] = []
    print(
        json.dumps(
            {
                "status": "starting",
                "device_id": args.device_id,
                "room_id": args.room_id,
                "sample_rate_hz": args.sample_rate_hz,
                "window_ms": args.window_ms,
                "raw_audio_persisted": False,
                "calibrated_db": False,
            },
            ensure_ascii=True,
        ),
        flush=True,
    )
    try:
        with sounddevice.InputStream(
            samplerate=args.sample_rate_hz,
            channels=1,
            dtype="float32",
            blocksize=block_frames,
            device=device,
        ) as stream:
            while args.windows == 0 or sent < args.windows:
                chunk, overflowed = stream.read(block_frames)
                try:
                    payload = build_feature_payload(
                        chunk,
                        room_id=args.room_id,
                        device_id=args.device_id,
                        window_ms=args.window_ms,
                    )
                finally:
                    del chunk
                try:
                    result = post_feature(args.url, token, payload)
                except (OSError, urllib.error.URLError, RuntimeError) as exc:
                    print(
                        json.dumps(
                            {
                                "status": "send_failed",
                                "error_type": type(exc).__name__,
                                "sample_id": payload["sample_id"],
                                "raw_audio_persisted": False,
                            },
                            ensure_ascii=True,
                        ),
                        file=sys.stderr,
                        flush=True,
                    )
                    time.sleep(0.25)
                    continue
                if args.diagnostic_summary:
                    diagnostic_rows.append(
                        {
                            name: payload[name]
                            for name in ("rms", "std", "peak")
                        }
                    )
                sent += 1
                print(
                    json.dumps(
                        {
                            "status": "sent",
                            "sample_id": result["sample_id"],
                            "summary_count": sent,
                            "input_overflowed": bool(overflowed),
                            "raw_audio_persisted": False,
                        },
                        ensure_ascii=True,
                    ),
                    flush=True,
                )
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "microphone_error",
                    "error_type": type(exc).__name__,
                    "raw_audio_persisted": False,
                },
                ensure_ascii=True,
            ),
            file=sys.stderr,
        )
        return 1
    if args.diagnostic_summary:
        print(
            json.dumps(
                {
                    "status": "diagnostic_summary",
                    "summary_count": len(diagnostic_rows),
                    "features": summarize_feature_rows(diagnostic_rows),
                    "raw_audio_persisted": False,
                    "calibrated_db": False,
                },
                ensure_ascii=True,
            ),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
