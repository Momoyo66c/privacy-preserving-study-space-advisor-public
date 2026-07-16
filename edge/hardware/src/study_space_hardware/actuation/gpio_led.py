"""Raspberry Pi RGB LED adapter using gpiozero."""

from __future__ import annotations

from typing import Any

from .status_mapper import StatusColor, map_room_state


_RGB_VALUES = {
    StatusColor.BLUE: (0, 0, 1),
    StatusColor.GREEN: (0, 1, 0),
    StatusColor.YELLOW: (1, 0.55, 0),
    StatusColor.RED: (1, 0, 0),
    StatusColor.WHITE: (1, 1, 1),
}


class GpioRgbLedIndicator:
    def __init__(
        self,
        *,
        red_pin: int,
        green_pin: int,
        blue_pin: int,
        active_high: bool = True,
        led: Any = None,
    ) -> None:
        if led is None:
            try:
                from gpiozero import RGBLED
            except ImportError as exc:
                raise RuntimeError(
                    "gpiozero is required for GPIO LED output"
                ) from exc
            led = RGBLED(
                red=red_pin,
                green=green_pin,
                blue=blue_pin,
                active_high=active_high,
            )
        self.led = led

    def set_state(self, room_state: str) -> None:
        signal = map_room_state(room_state)
        color = _RGB_VALUES[signal.color]
        if signal.flash and hasattr(self.led, "blink"):
            self.led.blink(
                on_time=0.3,
                off_time=0.3,
                on_color=color,
                off_color=(0, 0, 0),
                background=True,
            )
        else:
            self.led.color = color

    def close(self) -> None:
        self.led.off()
        self.led.close()
