from __future__ import annotations

from pathlib import Path

from study_space_hardware.remote_sound_supervisor import (
    build_agent_command,
    build_ssh_command,
)


def test_supervisor_builds_resilient_loopback_tunnel() -> None:
    command = build_ssh_command(
        ssh_executable="ssh",
        ssh_host="198.51.100.76",
        ssh_user="pi",
        identity_file=Path("id_ed25519"),
        local_port=18_766,
        remote_port=8_766,
    )

    assert command[0] == "ssh"
    assert "-4" in command
    assert "ExitOnForwardFailure=yes" in command
    assert "ServerAliveInterval=5" in command
    assert "ServerAliveCountMax=2" in command
    assert "127.0.0.1:18766:127.0.0.1:8766" in command
    assert command[-1] == "pi@198.51.100.76"


def test_supervisor_agent_command_contains_no_token_or_raw_audio() -> None:
    command = build_agent_command(
        python_executable="python",
        local_port=18_766,
        room_id="room_a",
        device_id="windows-laptop-mic",
        device=None,
        token_env="PSSA_REMOTE_SOUND_TOKEN",
    )
    joined = " ".join(command)

    assert "--max-consecutive-send-failures 3" in joined
    assert "--quiet-success" in command
    assert "PSSA_REMOTE_SOUND_TOKEN" in joined
    assert "secret-value" not in joined
    assert "pcm" not in joined.lower()
    assert "waveform" not in joined.lower()
