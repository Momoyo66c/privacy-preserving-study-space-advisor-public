"""Status-indicator protocol and a hardware-free logging implementation."""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from .status_mapper import StatusSignal, map_room_state


LOGGER = logging.getLogger(__name__)


@runtime_checkable
class StatusIndicator(Protocol):
    def set_state(self, room_state: str) -> None: ...

    def close(self) -> None: ...


class LoggingStatusIndicator:
    def __init__(self) -> None:
        self.last_signal: StatusSignal | None = None

    def set_state(self, room_state: str) -> None:
        self.last_signal = map_room_state(room_state)
        LOGGER.info(
            "status_indicator color=%s flash=%s",
            self.last_signal.color.value,
            str(self.last_signal.flash).lower(),
        )

    def close(self) -> None:
        self.last_signal = None
