"""Pure mapping from the shared room-state enum to local indicator signals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class StatusColor(StrEnum):
    BLUE = "blue"
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    WHITE = "white"


@dataclass(frozen=True, slots=True)
class StatusSignal:
    color: StatusColor
    flash: bool = False


_ROOM_STATE_SIGNALS = {
    "empty_or_low_activity": StatusSignal(StatusColor.BLUE),
    "quiet_study_recommended": StatusSignal(StatusColor.GREEN),
    "discussion_allowed": StatusSignal(StatusColor.YELLOW),
    "not_recommended_noisy_or_crowded": StatusSignal(StatusColor.RED),
    "unknown": StatusSignal(StatusColor.WHITE, flash=True),
}


def map_room_state(room_state: str) -> StatusSignal:
    """Map every supported state; unrecognized values fail safe to white flash."""

    return _ROOM_STATE_SIGNALS.get(
        room_state,
        StatusSignal(StatusColor.WHITE, flash=True),
    )
