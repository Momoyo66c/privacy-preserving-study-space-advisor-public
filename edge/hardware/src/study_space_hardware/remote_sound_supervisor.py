"""Resilient Windows launcher for the privacy-safe remote microphone agent.

The supervisor owns both the SSH loopback forward and the microphone agent.
It never reads audio itself and never receives the bearer token as a command
line argument.  When either child exits, both are rebuilt so a stale tunnel or
audio device cannot leave the dashboard silently offline.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Sequence


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def default_log_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "PSSA" / "remote-sound-supervisor.log"
    return Path.home() / ".local" / "state" / "pssa" / "remote-sound-supervisor.log"


def build_ssh_command(
    *,
    ssh_executable: str,
    ssh_host: str,
    ssh_user: str,
    identity_file: Path,
    local_port: int,
    remote_port: int,
) -> list[str]:
    """Build a non-interactive tunnel with fast dead-connection detection."""

    return [
        ssh_executable,
        "-4",
        "-N",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=5",
        "-o",
        "ServerAliveCountMax=2",
        "-o",
        "TCPKeepAlive=yes",
        "-o",
        "ConnectTimeout=8",
        "-o",
        "ConnectionAttempts=1",
        "-i",
        str(identity_file),
        "-L",
        f"127.0.0.1:{local_port}:127.0.0.1:{remote_port}",
        f"{ssh_user}@{ssh_host}",
    ]


def build_agent_command(
    *,
    python_executable: str,
    local_port: int,
    room_id: str,
    device_id: str,
    device: str | None,
    token_env: str,
) -> list[str]:
    command = [
        python_executable,
        "-m",
        "study_space_hardware.remote_sound_agent",
        "--url",
        f"http://127.0.0.1:{local_port}/v1/sound-features",
        "--room-id",
        room_id,
        "--device-id",
        device_id,
        "--token-env",
        token_env,
        "--max-consecutive-send-failures",
        "3",
        "--quiet-success",
    ]
    if device:
        command.extend(["--device", device])
    return command


def _write_event(log: IO[str], status: str, **details: object) -> None:
    row = {
        "timestamp": _utc_now(),
        "status": status,
        "raw_audio_persisted": False,
        **details,
    }
    line = json.dumps(row, ensure_ascii=True, separators=(",", ":"))
    print(line, flush=True)
    log.write(line + "\n")
    log.flush()


def _rotate_log(path: Path, max_bytes: int = 5 * 1024 * 1024) -> None:
    if not path.exists() or path.stat().st_size < max_bytes:
        return
    previous = path.with_suffix(path.suffix + ".previous")
    previous.unlink(missing_ok=True)
    path.replace(previous)


def _port_ready(port: int, timeout_s: float = 0.2) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout_s):
            return True
    except OSError:
        return False


def _stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Keep the Windows microphone summary agent and its loopback SSH "
            "tunnel alive. No raw audio is stored or transmitted."
        )
    )
    parser.add_argument(
        "--ssh-host",
        default=os.environ.get("PSSA_PI_HOST", "raspberrypi.local"),
    )
    parser.add_argument("--ssh-user", default=os.environ.get("PSSA_PI_USER", "pi"))
    parser.add_argument(
        "--identity-file",
        type=Path,
        default=Path.home() / ".ssh" / "id_ed25519",
    )
    parser.add_argument("--local-port", type=int, default=18_766)
    parser.add_argument("--remote-port", type=int, default=8_766)
    parser.add_argument("--room-id", default="room_a")
    parser.add_argument("--device-id", default="windows-laptop-mic")
    parser.add_argument(
        "--device",
        default=None,
        help="optional sounddevice input index or name; default follows Windows",
    )
    parser.add_argument("--token-env", default="PSSA_REMOTE_SOUND_TOKEN")
    parser.add_argument("--ready-timeout-seconds", type=float, default=12.0)
    parser.add_argument("--restart-delay-seconds", type=float, default=1.0)
    parser.add_argument("--max-restart-delay-seconds", type=float, default=30.0)
    parser.add_argument("--log-file", type=Path, default=default_log_path())
    parser.add_argument(
        "--once",
        action="store_true",
        help="run one tunnel/agent lifecycle; intended for diagnostics",
    )
    return parser


def _validate_args(args: argparse.Namespace) -> str:
    if not args.ssh_host or any(char.isspace() for char in args.ssh_host):
        raise ValueError("ssh-host must be a non-empty host name or IP address")
    if not args.ssh_user or any(char.isspace() for char in args.ssh_user):
        raise ValueError("ssh-user must be a non-empty account name")
    if not 1 <= args.local_port <= 65_535 or not 1 <= args.remote_port <= 65_535:
        raise ValueError("local-port and remote-port must be from 1 to 65535")
    if args.ready_timeout_seconds <= 0:
        raise ValueError("ready-timeout-seconds must be positive")
    if args.restart_delay_seconds <= 0:
        raise ValueError("restart-delay-seconds must be positive")
    if args.max_restart_delay_seconds < args.restart_delay_seconds:
        raise ValueError(
            "max-restart-delay-seconds must be at least restart-delay-seconds"
        )
    identity = args.identity_file.expanduser().resolve()
    if not identity.is_file():
        raise ValueError(f"SSH identity file does not exist: {identity}")
    args.identity_file = identity
    token = os.environ.get(args.token_env, "")
    if len(token) < 24 or any(char.isspace() for char in token):
        raise ValueError(
            f"{args.token_env} must contain at least 24 non-space characters"
        )
    ssh_executable = shutil.which("ssh")
    if ssh_executable is None:
        raise ValueError("OpenSSH client was not found on PATH")
    return ssh_executable


def run(args: argparse.Namespace) -> int:
    ssh_executable = _validate_args(args)
    log_path = args.log_file.expanduser().resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _rotate_log(log_path)
    delay = args.restart_delay_seconds
    attempt = 0

    with log_path.open("a", encoding="utf-8", buffering=1) as log:
        _write_event(
            log,
            "supervisor_starting",
            ssh_host=args.ssh_host,
            room_id=args.room_id,
            device_id=args.device_id,
        )
        while True:
            attempt += 1
            tunnel: subprocess.Popen[bytes] | None = None
            agent: subprocess.Popen[bytes] | None = None
            try:
                if _port_ready(args.local_port):
                    raise RuntimeError(
                        f"local port {args.local_port} is already in use"
                    )
                ssh_command = build_ssh_command(
                    ssh_executable=ssh_executable,
                    ssh_host=args.ssh_host,
                    ssh_user=args.ssh_user,
                    identity_file=args.identity_file,
                    local_port=args.local_port,
                    remote_port=args.remote_port,
                )
                tunnel = subprocess.Popen(
                    ssh_command,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW
                        if sys.platform == "win32"
                        else 0
                    ),
                )
                deadline = time.monotonic() + args.ready_timeout_seconds
                while time.monotonic() < deadline:
                    if tunnel.poll() is not None:
                        raise RuntimeError(
                            f"SSH tunnel exited with code {tunnel.returncode}"
                        )
                    if _port_ready(args.local_port):
                        break
                    time.sleep(0.2)
                else:
                    raise RuntimeError("SSH tunnel did not become ready")

                agent_command = build_agent_command(
                    python_executable=sys.executable,
                    local_port=args.local_port,
                    room_id=args.room_id,
                    device_id=args.device_id,
                    device=args.device,
                    token_env=args.token_env,
                )
                agent = subprocess.Popen(
                    agent_command,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW
                        if sys.platform == "win32"
                        else 0
                    ),
                )
                _write_event(log, "pipeline_ready", attempt=attempt)
                delay = args.restart_delay_seconds
                while tunnel.poll() is None and agent.poll() is None:
                    time.sleep(0.5)
                if tunnel.poll() is not None:
                    _write_event(
                        log,
                        "tunnel_exited",
                        attempt=attempt,
                        exit_code=tunnel.returncode,
                    )
                if agent.poll() is not None:
                    _write_event(
                        log,
                        "microphone_agent_exited",
                        attempt=attempt,
                        exit_code=agent.returncode,
                    )
            except KeyboardInterrupt:
                _write_event(log, "supervisor_stopping", reason="keyboard_interrupt")
                return 0
            except Exception as exc:
                _write_event(
                    log,
                    "pipeline_unavailable",
                    attempt=attempt,
                    error_type=type(exc).__name__,
                    message=str(exc),
                )
            finally:
                _stop_process(agent)
                _stop_process(tunnel)

            if args.once:
                return 1
            _write_event(
                log,
                "pipeline_restart_scheduled",
                attempt=attempt,
                delay_seconds=delay,
            )
            time.sleep(delay)
            delay = min(delay * 2.0, args.max_restart_delay_seconds)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return run(args)
    except ValueError as exc:
        print(
            json.dumps(
                {
                    "status": "configuration_error",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "raw_audio_persisted": False,
                },
                ensure_ascii=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
