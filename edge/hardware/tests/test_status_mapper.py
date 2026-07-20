from study_space_hardware.actuation.base import LoggingStatusIndicator
from study_space_hardware.actuation.gpio_led import GpioRgbLedIndicator
from study_space_hardware.actuation.microbit import MicrobitSerialIndicator
from study_space_hardware.actuation.status_mapper import StatusColor, map_room_state


class FakeLed:
    def __init__(self) -> None:
        self.color = None
        self.blink_args = None
        self.off_called = False
        self.close_called = False

    def blink(self, **kwargs) -> None:
        self.blink_args = kwargs

    def off(self) -> None:
        self.off_called = True

    def close(self) -> None:
        self.close_called = True


class FakeSerial:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, value: bytes) -> None:
        self.writes.append(value)

    def close(self) -> None:
        self.closed = True


def test_every_contract_state_has_deterministic_mapping() -> None:
    assert map_room_state("empty_or_low_activity").color is StatusColor.BLUE
    assert map_room_state("quiet_study_recommended").color is StatusColor.GREEN
    assert map_room_state("discussion_allowed").color is StatusColor.YELLOW
    assert (
        map_room_state("not_recommended_noisy_or_crowded").color
        is StatusColor.RED
    )
    unknown = map_room_state("unknown")
    assert unknown.color is StatusColor.WHITE
    assert unknown.flash is True


def test_unknown_string_fails_safe() -> None:
    indicator = LoggingStatusIndicator()
    indicator.set_state("unrecognized")
    assert indicator.last_signal is not None
    assert indicator.last_signal.color is StatusColor.WHITE
    assert indicator.last_signal.flash is True


def test_gpio_adapter_uses_injected_led_and_releases_it() -> None:
    led = FakeLed()
    indicator = GpioRgbLedIndicator(
        red_pin=17,
        green_pin=27,
        blue_pin=22,
        led=led,
    )
    indicator.set_state("quiet_study_recommended")
    assert led.color == (0, 1, 0)
    indicator.set_state("unknown")
    assert led.blink_args["background"] is True
    indicator.close()
    assert led.off_called is True
    assert led.close_called is True


def test_microbit_adapter_sends_only_status_command_and_closes() -> None:
    serial = FakeSerial()
    indicator = MicrobitSerialIndicator(serial_factory=lambda: serial)
    indicator.set_state("discussion_allowed")
    assert serial.writes == [b"STATUS yellow 0\n"]
    indicator.close()
    assert serial.closed is True
