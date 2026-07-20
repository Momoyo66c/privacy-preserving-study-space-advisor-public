"""Local-only live MLX90640 heat-map viewer.

The viewer retains exactly one thermal frame in memory and serves it to a
browser on a loopback HTTP endpoint.  It does not persist frames, contact the
backend, or expose the server beyond localhost unless the operator explicitly
changes ``--host``.
"""

from __future__ import annotations

import argparse
import json
import logging
import threading
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .bootstrap import build_real_drivers
from .clock import SystemClock
from .config import HardwareConfig, load_config
from .drivers.base import SensorDriver
from .models import THERMAL_HEIGHT, THERMAL_PIXELS, THERMAL_WIDTH, SensorSample
from .simulators.sensors import build_simulated_drivers


LOGGER = logging.getLogger(__name__)


class ThermalFrameStore:
    """Thread-safe, single-frame in-memory store for the local viewer."""

    def __init__(self, *, room_id: str, device_id: str) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "schema_version": "1.0",
            "status": "starting",
            "sequence": 0,
            "room_id": room_id,
            "device_id": device_id,
            "captured_at": None,
            "width": THERMAL_WIDTH,
            "height": THERMAL_HEIGHT,
            "values": [],
            "minimum_c": None,
            "maximum_c": None,
            "mean_c": None,
            "error": None,
        }

    def publish(self, sample: SensorSample) -> None:
        """Replace the previous frame after validating the thermal shape."""

        if sample.sensor != "thermal":
            raise ValueError("live thermal viewer only accepts thermal samples")
        values = tuple(float(value) for value in sample.values["temperatures_c"])
        width = int(sample.values.get("width", THERMAL_WIDTH))
        height = int(sample.values.get("height", THERMAL_HEIGHT))
        if width != THERMAL_WIDTH or height != THERMAL_HEIGHT:
            raise ValueError("thermal frame must be 32 x 24")
        if len(values) != THERMAL_PIXELS:
            raise ValueError("thermal frame must contain 768 values")

        with self._lock:
            sequence = int(self._state["sequence"]) + 1
            self._state = {
                **self._state,
                "status": "ready",
                "sequence": sequence,
                "captured_at": sample.captured_at.astimezone(timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
                "values": values,
                "minimum_c": min(values),
                "maximum_c": max(values),
                "mean_c": sum(values) / len(values),
                "error": None,
            }

    def mark_connecting(self) -> None:
        with self._lock:
            self._state = {**self._state, "status": "connecting", "error": None}

    def mark_error(self, message: str) -> None:
        with self._lock:
            self._state = {**self._state, "status": "error", "error": message}

    def snapshot(self) -> dict[str, Any]:
        """Return an HTTP-serializable copy without exposing mutable state."""

        with self._lock:
            result = dict(self._state)
            result["values"] = list(self._state["values"])
            return result


class ThermalCapture:
    """Continuously read one thermal driver into a single-frame store."""

    def __init__(
        self,
        driver: SensorDriver,
        store: ThermalFrameStore,
        *,
        retry_delay_s: float = 0.5,
    ) -> None:
        self._driver = driver
        self._store = store
        self._retry_delay_s = retry_delay_s
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="live-thermal-capture",
            daemon=True,
        )
        self._thread.start()

    def close(self) -> None:
        self._stop_event.set()
        try:
            self._driver.close()
        finally:
            if self._thread is not None:
                self._thread.join(timeout=3.0)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._store.mark_connecting()
            try:
                self._driver.start()
                break
            except Exception as exc:
                self._store.mark_error(f"{type(exc).__name__}: {exc}")
                self._driver.close()
                self._stop_event.wait(self._retry_delay_s)
        else:
            return

        try:
            while not self._stop_event.is_set():
                try:
                    self._store.publish(self._driver.read())
                except Exception as exc:
                    if not self._stop_event.is_set():
                        self._store.mark_error(f"{type(exc).__name__}: {exc}")
                        self._stop_event.wait(self._retry_delay_s)
        finally:
            self._driver.close()


def dashboard_html(*, refresh_ms: int) -> str:
    """Return a dependency-free dashboard document for the local server."""

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MLX90640 实时热成像</title>
  <style>
    :root {{ color-scheme: light dark; --bg:#f4f4f1; --panel:#fff; --text:#171714;
      --muted:#686862; --line:#d8d8d0; --accent:#146c5a; --bad:#b42318; }}
    @media (prefers-color-scheme: dark) {{ :root {{ --bg:#111210; --panel:#1b1d1a;
      --text:#f4f4ef; --muted:#a8aaa3; --line:#343730; --accent:#63d3b8; --bad:#ff8a80; }} }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; min-height:100vh; background:var(--bg); color:var(--text);
      font:15px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }}
    main {{ width:min(960px,100%); margin:0 auto; padding:24px; }}
    header {{ display:flex; justify-content:space-between; gap:16px; align-items:end;
      margin-bottom:16px; }}
    h1 {{ margin:0; font:600 clamp(20px,4vw,30px)/1.15 system-ui,sans-serif; }}
    .sub {{ color:var(--muted); margin-top:5px; }}
    .status {{ display:flex; align-items:center; gap:8px; color:var(--muted); white-space:nowrap; }}
    .dot {{ width:9px; height:9px; border-radius:50%; background:var(--muted); }}
    .ready .dot {{ background:var(--accent); }} .error .dot {{ background:var(--bad); }}
    .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:16px; }}
    .canvas-wrap {{ position:relative; width:100%; aspect-ratio:4/3; background:#090b0a;
      border-radius:8px; overflow:hidden; }}
    canvas {{ width:100%; height:100%; display:block; image-rendering:pixelated; }}
    canvas.smooth {{ image-rendering:auto; }}
    .tooltip {{ display:none; position:absolute; pointer-events:none; transform:translate(10px,10px);
      padding:5px 7px; background:#0d0f0e; color:#fff; border:1px solid #525750;
      border-radius:5px; font-size:12px; }}
    .metrics {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-top:12px; }}
    .metric {{ border:1px solid var(--line); border-radius:8px; padding:10px; min-width:0; }}
    .label {{ color:var(--muted); font-size:12px; }} .value {{ margin-top:3px; font-size:17px; }}
    .legend {{ display:flex; align-items:center; gap:10px; margin-top:12px; color:var(--muted); font-size:12px; }}
    .scale {{ height:10px; flex:1; border-radius:5px; background:linear-gradient(90deg,
      #171b5c,#2059a8,#159c91,#8fbd3f,#f4b52f,#eb5a2a,#7d0828); }}
    .toolbar {{ display:flex; justify-content:space-between; gap:12px; align-items:center; margin-top:12px; }}
    button {{ min-height:40px; padding:0 13px; border:1px solid var(--line); border-radius:8px;
      background:var(--panel); color:var(--text); font:inherit; cursor:pointer; }}
    button:hover {{ border-color:var(--accent); }} button:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px; }}
    .privacy {{ color:var(--muted); font-size:12px; text-align:right; }}
    @media (max-width:640px) {{ main {{ padding:14px; }} header {{ align-items:start; flex-direction:column; }}
      .metrics {{ grid-template-columns:repeat(2,1fr); }} .toolbar {{ align-items:stretch; flex-direction:column; }}
      .privacy {{ text-align:left; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <div><h1>MLX90640 实时热成像</h1><div class="sub" id="identity">等待设备信息</div></div>
    <div class="status" id="status" role="status" aria-live="polite"><span class="dot"></span><span>连接中</span></div>
  </header>
  <section class="panel" aria-label="实时热阵列">
    <div class="canvas-wrap" id="wrap"><canvas id="heat" width="32" height="24" aria-label="32乘24热成像画面"></canvas><div class="tooltip" id="tip"></div></div>
    <div class="metrics">
      <div class="metric"><div class="label">最低温</div><div class="value" id="min">—</div></div>
      <div class="metric"><div class="label">平均温</div><div class="value" id="mean">—</div></div>
      <div class="metric"><div class="label">最高温</div><div class="value" id="max">—</div></div>
      <div class="metric"><div class="label">帧序号</div><div class="value" id="seq">—</div></div>
    </div>
    <div class="legend"><span id="lo">低</span><div class="scale" aria-hidden="true"></div><span id="hi">高</span></div>
    <div class="toolbar"><button id="smooth" type="button" aria-pressed="false">平滑显示：关</button><div class="privacy">仅内存保留最新一帧 · 不写文件 · 每 {refresh_ms} ms 刷新</div></div>
  </section>
</main>
<script>
  const canvas=document.getElementById('heat'),ctx=canvas.getContext('2d'),tip=document.getElementById('tip');
  const wrap=document.getElementById('wrap'); let frame=null;
  const stops=[[0,[23,27,92]],[.18,[32,89,168]],[.38,[21,156,145]],[.58,[143,189,63]],[.76,[244,181,47]],[.9,[235,90,42]],[1,[125,8,40]]];
  function color(t){{ t=Math.max(0,Math.min(1,t)); let a=stops[0],b=stops.at(-1);
    for(let i=1;i<stops.length;i++){{if(t<=stops[i][0]){{a=stops[i-1];b=stops[i];break;}}}}
    const p=(t-a[0])/(b[0]-a[0]||1); return a[1].map((v,i)=>Math.round(v+(b[1][i]-v)*p)); }}
  function draw(data){{ const values=data.values,min=data.minimum_c,max=data.maximum_c,span=Math.max(.01,max-min);
    const image=ctx.createImageData(32,24); values.forEach((v,i)=>{{const c=color((v-min)/span),o=i*4; image.data[o]=c[0];image.data[o+1]=c[1];image.data[o+2]=c[2];image.data[o+3]=255;}});ctx.putImageData(image,0,0); }}
  function text(id,value){{document.getElementById(id).textContent=value;}}
  async function update(){{ try{{const response=await fetch('/frame',{{cache:'no-store'}});const data=await response.json();
    const status=document.getElementById('status');status.className='status '+data.status;status.lastElementChild.textContent=data.status==='ready'?'实时':data.status==='error'?'读取异常':'连接中';
    text('identity',data.room_id+' · '+data.device_id);if(data.status==='ready'&&data.values.length===768){{frame=data;draw(data);text('min',data.minimum_c.toFixed(1)+' °C');text('mean',data.mean_c.toFixed(1)+' °C');text('max',data.maximum_c.toFixed(1)+' °C');text('seq',data.sequence);text('lo',data.minimum_c.toFixed(1)+' °C');text('hi',data.maximum_c.toFixed(1)+' °C');}}
    else if(data.error){{text('identity',data.error);}} }}catch(error){{const status=document.getElementById('status');status.className='status error';status.lastElementChild.textContent='服务不可达';}} }}
  wrap.addEventListener('pointermove',event=>{{if(!frame)return;const r=canvas.getBoundingClientRect(),x=Math.min(31,Math.max(0,Math.floor((event.clientX-r.left)/r.width*32))),y=Math.min(23,Math.max(0,Math.floor((event.clientY-r.top)/r.height*24)));tip.textContent=`(${{x}}, ${{y}}) ${{frame.values[y*32+x].toFixed(1)}} °C`;tip.style.display='block';tip.style.left=(event.clientX-r.left)+'px';tip.style.top=(event.clientY-r.top)+'px';}});
  wrap.addEventListener('pointerleave',()=>tip.style.display='none');document.getElementById('smooth').addEventListener('click',event=>{{const on=canvas.classList.toggle('smooth');event.currentTarget.setAttribute('aria-pressed',String(on));event.currentTarget.textContent='平滑显示：'+(on?'开':'关');}});
  update();setInterval(update,{refresh_ms});
</script>
</body>
</html>"""


def make_handler(
    store: ThermalFrameStore,
    *,
    refresh_ms: int,
) -> type[BaseHTTPRequestHandler]:
    """Create an HTTP handler bound to one frame store."""

    html = dashboard_html(refresh_ms=refresh_ms).encode("utf-8")

    class ThermalRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib HTTP API
            path = self.path.partition("?")[0]
            if path == "/":
                self._send(HTTPStatus.OK, "text/html; charset=utf-8", html)
                return
            if path in {"/frame", "/health"}:
                snapshot = store.snapshot()
                if path == "/health":
                    snapshot = {
                        "status": snapshot["status"],
                        "sequence": snapshot["sequence"],
                        "captured_at": snapshot["captured_at"],
                        "error": snapshot["error"],
                    }
                body = json.dumps(
                    snapshot,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                self._send(HTTPStatus.OK, "application/json; charset=utf-8", body)
                return
            self._send(
                HTTPStatus.NOT_FOUND,
                "application/json; charset=utf-8",
                b'{"error":"not_found"}',
            )

        def _send(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'unsafe-inline'; "
                "style-src 'unsafe-inline'; connect-src 'self'; "
                "img-src 'self' data:; object-src 'none'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            LOGGER.debug("viewer request: " + format, *args)

    return ThermalRequestHandler


def build_thermal_driver(config: HardwareConfig) -> SensorDriver:
    """Build only the configured thermal driver from the existing stack."""

    clock = SystemClock()
    drivers: Mapping[str, SensorDriver]
    if config.simulator.enabled:
        drivers = build_simulated_drivers(config, clock)
    else:
        drivers = build_real_drivers(config, clock)
    try:
        return drivers["thermal"]
    except KeyError as exc:
        raise ValueError("thermal sensor must be enabled in the configuration") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Serve a continuously refreshing local MLX90640 heat map"
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--refresh-ms", type=int, default=500)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if not 250 <= args.refresh_ms <= 5000:
        parser.error("--refresh-ms must be between 250 and 5000")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s level=%(levelname)s message=%(message)s",
    )
    config = load_config(args.config)
    store = ThermalFrameStore(room_id=config.room_id, device_id=config.device_id)
    capture = ThermalCapture(build_thermal_driver(config), store)
    server = ThreadingHTTPServer(
        (args.host, args.port),
        make_handler(store, refresh_ms=args.refresh_ms),
    )
    server.daemon_threads = True
    capture.start()
    LOGGER.info("live thermal viewer: http://%s:%d", args.host, args.port)
    LOGGER.info("frames stay in memory; no thermal frame is written to disk")
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        LOGGER.info("stopping live thermal viewer")
    finally:
        server.server_close()
        capture.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
