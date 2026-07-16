"""micro:bit serial status adapter.

The companion micro:bit program only needs to accept newline-delimited messages
such as ``STATUS green 0``. No sensor payload or identifying data is sent.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .status_mapper import map_room_state


class MicrobitSerialIndicator:
    def __init__(
        self,
        *,
        port: str = "/dev/ttyACM0",
        baud_rate: int = 115_200,
        serial_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.port = port
        self.baud_rate = baud_rate
        self._serial_factory = serial_factory
        self._serial: Any = None

    def _ensure_open(self) -> None:
        if self._serial is not None:
            return
        if self._serial_factory is not None:
            self._serial = self._serial_factory()
            return
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError("pyserial is required for micro:bit output") from exc
        self._serial = serial.Serial(
            self.port,
            self.baud_rate,
            timeout=0.5,
        )

    def set_state(self, room_state: str) -> None:
        self._ensure_open()
        signal = map_room_state(room_state)
        command = f"STATUS {signal.color.value} {int(signal.flash)}\n"
        self._serial.write(command.encode("ascii"))

    def close(self) -> None:
        if self._serial is not None and hasattr(self._serial, "close"):
            self._serial.close()
        self._serial = None
