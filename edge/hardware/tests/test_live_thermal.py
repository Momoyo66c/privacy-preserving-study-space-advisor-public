from __future__ import annotations

import json
import struct
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer

from study_space_hardware.live_thermal import (
    ThermalFrameStore,
    dashboard_html,
    encode_binary_frame,
    make_handler,
)
from study_space_hardware.models import SampleQuality, SensorSample


def _thermal_sample(offset: float = 0.0) -> SensorSample:
    values = tuple(20.0 + offset + index / 100.0 for index in range(768))
    return SensorSample(
        sensor="thermal",
        captured_at=datetime(2026, 7, 20, 9, 0, tzinfo=timezone.utc),
        monotonic_s=1.0,
        values={"temperatures_c": values, "width": 32, "height": 24},
        units={"temperatures_c": "celsius"},
        quality=SampleQuality.VALID,
        source="test",
    )


def test_frame_store_keeps_only_latest_valid_frame() -> None:
    capture_times = iter((1.0, 1.5))
    store = ThermalFrameStore(
        room_id="room_a",
        device_id="pi5-a",
        monotonic=lambda: next(capture_times),
    )
    store.publish(_thermal_sample())
    store.publish(_thermal_sample(1.0))

    frame = store.snapshot()

    assert frame["status"] == "ready"
    assert frame["sequence"] == 2
    assert len(frame["values"]) == 768
    assert frame["values"][0] == 21.0
    assert frame["minimum_c"] == 21.0
    assert frame["maximum_c"] == 28.67
    assert frame["capture_fps"] == 2.0
    assert "audio" not in json.dumps(frame)


def test_dashboard_is_self_contained_and_continuously_refreshes() -> None:
    html = dashboard_html(render_fps=60)

    assert "requestAnimationFrame(render)" in html
    assert "fetch('/frame.bin?after='+sequence" in html
    assert "new DataView(buffer)" in html
    assert "60 FPS 插值渲染" in html
    assert "<canvas" in html
    assert 'aria-pressed="true">平滑显示：开' in html
    assert "setInterval(" not in html
    assert "http://" not in html
    assert "https://" not in html


def test_binary_frame_uses_little_endian_centi_degrees() -> None:
    store = ThermalFrameStore(room_id="room_a", device_id="pi5-a")
    store.publish(_thermal_sample())

    encoded = encode_binary_frame(store.snapshot())

    assert len(encoded) == 768 * 2
    values = struct.unpack("<768h", encoded)
    assert values[0] == 2000
    assert values[-1] == 2767


def test_http_endpoints_disable_caching_and_do_not_expose_frames_in_health() -> None:
    store = ThermalFrameStore(room_id="room_a", device_id="pi5-a")
    store.publish(_thermal_sample())
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        make_handler(store, render_fps=60, wait_timeout_s=0.01),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/frame") as response:
            frame = json.load(response)
            assert response.headers["Cache-Control"] == "no-store, max-age=0"
            assert len(frame["values"]) == 768
        with urllib.request.urlopen(base + "/frame.bin?after=0") as response:
            body = response.read()
            assert response.status == 200
            assert response.headers["Content-Type"] == "application/octet-stream"
            assert response.headers["X-Thermal-Width"] == "32"
            assert response.headers["X-Thermal-Height"] == "24"
            assert response.headers["X-Thermal-Sequence"] == "1"
            assert len(body) == 768 * 2
            assert struct.unpack("<h", body[:2])[0] == 2000
        with urllib.request.urlopen(base + "/frame.bin?after=1") as response:
            assert response.status == 204
            assert response.read() == b""
        with urllib.request.urlopen(base + "/health") as response:
            health = json.load(response)
            assert health["status"] == "ready"
            assert health["room_id"] == "room_a"
            assert health["device_id"] == "pi5-a"
            assert "capture_fps" in health
            assert "values" not in health
        try:
            urllib.request.urlopen(base + "/frame.bin?after=bad")
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
        else:
            raise AssertionError("invalid sequence must return 400")
        try:
            urllib.request.urlopen(base + "/missing")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
        else:
            raise AssertionError("missing endpoint must return 404")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)
