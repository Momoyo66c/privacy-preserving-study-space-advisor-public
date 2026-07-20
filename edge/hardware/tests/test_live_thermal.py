from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer

from study_space_hardware.live_thermal import (
    ThermalFrameStore,
    dashboard_html,
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
    store = ThermalFrameStore(room_id="room_a", device_id="pi5-a")
    store.publish(_thermal_sample())
    store.publish(_thermal_sample(1.0))

    frame = store.snapshot()

    assert frame["status"] == "ready"
    assert frame["sequence"] == 2
    assert len(frame["values"]) == 768
    assert frame["values"][0] == 21.0
    assert frame["minimum_c"] == 21.0
    assert frame["maximum_c"] == 28.67
    assert "audio" not in json.dumps(frame)


def test_dashboard_is_self_contained_and_continuously_refreshes() -> None:
    html = dashboard_html(refresh_ms=500)

    assert "setInterval(update,500)" in html
    assert "fetch('/frame'" in html
    assert "<canvas" in html
    assert "平滑显示" in html
    assert "http://" not in html
    assert "https://" not in html


def test_http_endpoints_disable_caching_and_do_not_expose_frames_in_health() -> None:
    store = ThermalFrameStore(room_id="room_a", device_id="pi5-a")
    store.publish(_thermal_sample())
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store, refresh_ms=500))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/frame") as response:
            frame = json.load(response)
            assert response.headers["Cache-Control"] == "no-store, max-age=0"
            assert len(frame["values"]) == 768
        with urllib.request.urlopen(base + "/health") as response:
            health = json.load(response)
            assert health["status"] == "ready"
            assert "values" not in health
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
