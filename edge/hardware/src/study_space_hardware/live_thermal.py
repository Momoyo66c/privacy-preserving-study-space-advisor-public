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
import struct
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .bootstrap import build_real_drivers
from .clock import SystemClock
from .config import HardwareConfig, load_config
from .drivers.base import SensorDriver
from .models import THERMAL_HEIGHT, THERMAL_PIXELS, THERMAL_WIDTH, SensorSample
from .simulators.sensors import build_simulated_drivers


LOGGER = logging.getLogger(__name__)


class ThermalFrameStore:
    """Thread-safe, single-frame in-memory store for the local viewer."""

    def __init__(
        self,
        *,
        room_id: str,
        device_id: str,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._condition = threading.Condition()
        self._monotonic = monotonic
        self._capture_times: deque[float] = deque(maxlen=120)
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

        with self._condition:
            sequence = int(self._state["sequence"]) + 1
            self._capture_times.append(self._monotonic())
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
            self._condition.notify_all()

    def mark_connecting(self) -> None:
        with self._condition:
            self._state = {**self._state, "status": "connecting", "error": None}
            self._condition.notify_all()

    def mark_error(self, message: str) -> None:
        with self._condition:
            self._state = {**self._state, "status": "error", "error": message}
            self._condition.notify_all()

    def snapshot(self) -> dict[str, Any]:
        """Return an HTTP-serializable copy without exposing mutable state."""

        with self._condition:
            return self._snapshot_locked()

    def wait_for_newer(
        self,
        sequence: int,
        *,
        timeout_s: float = 1.0,
    ) -> dict[str, Any]:
        """Wait briefly for a newer frame, then return the latest snapshot."""

        with self._condition:
            self._condition.wait_for(
                lambda: int(self._state["sequence"]) > sequence,
                timeout=timeout_s,
            )
            return self._snapshot_locked()

    def _snapshot_locked(self) -> dict[str, Any]:
        result = dict(self._state)
        result["values"] = list(self._state["values"])
        if len(self._capture_times) < 2:
            result["capture_fps"] = 0.0
        else:
            elapsed = self._capture_times[-1] - self._capture_times[0]
            result["capture_fps"] = (
                (len(self._capture_times) - 1) / elapsed if elapsed > 0 else 0.0
            )
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


def dashboard_html(*, render_fps: int = 60) -> str:
    """Return a dependency-free, temporally smoothed dashboard document."""

    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MLX90640 实时热成像</title>
  <style>
    :root { color-scheme:light dark; --bg:#f4f4f1; --panel:#fff; --text:#171714;
      --muted:#686862; --line:#d8d8d0; --accent:#146c5a; --bad:#b42318; }
    @media (prefers-color-scheme:dark) { :root { --bg:#111210; --panel:#1b1d1a;
      --text:#f4f4ef; --muted:#a8aaa3; --line:#343730; --accent:#63d3b8; --bad:#ff8a80; } }
    * { box-sizing:border-box; }
    body { margin:0; min-height:100vh; background:var(--bg); color:var(--text);
      font:15px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }
    main { width:min(960px,100%); margin:0 auto; padding:24px; }
    header { display:flex; justify-content:space-between; gap:16px; align-items:end; margin-bottom:16px; }
    h1 { margin:0; font:600 clamp(20px,4vw,30px)/1.15 system-ui,sans-serif; }
    .sub { color:var(--muted); margin-top:5px; }
    .status { display:flex; align-items:center; gap:8px; color:var(--muted); white-space:nowrap; }
    .dot { width:9px; height:9px; border-radius:50%; background:var(--muted); }
    .ready .dot { background:var(--accent); } .error .dot { background:var(--bad); }
    .panel { background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:16px; }
    .canvas-wrap { position:relative; width:100%; aspect-ratio:4/3; background:#090b0a;
      border-radius:8px; overflow:hidden; }
    canvas { width:100%; height:100%; display:block; image-rendering:pixelated; }
    canvas.smooth { image-rendering:auto; }
    .tooltip { display:none; position:absolute; pointer-events:none; transform:translate(10px,10px);
      padding:5px 7px; background:#0d0f0e; color:#fff; border:1px solid #525750;
      border-radius:5px; font-size:12px; }
    .metrics { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-top:12px; }
    .metric { border:1px solid var(--line); border-radius:8px; padding:10px; min-width:0; }
    .label { color:var(--muted); font-size:12px; } .value { margin-top:3px; font-size:17px; }
    .legend { display:flex; align-items:center; gap:10px; margin-top:12px; color:var(--muted); font-size:12px; }
    .scale { height:10px; flex:1; border-radius:5px; background:linear-gradient(90deg,
      #171b5c,#2059a8,#159c91,#8fbd3f,#f4b52f,#eb5a2a,#7d0828); }
    .toolbar { display:flex; justify-content:space-between; gap:12px; align-items:center; margin-top:12px; }
    button { min-height:40px; padding:0 13px; border:1px solid var(--line); border-radius:8px;
      background:var(--panel); color:var(--text); font:inherit; cursor:pointer; }
    button:hover { border-color:var(--accent); } button:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
    .privacy { color:var(--muted); font-size:12px; text-align:right; }
    @media (max-width:640px) { main { padding:14px; } header { align-items:start; flex-direction:column; }
      .metrics { grid-template-columns:repeat(2,1fr); } .toolbar { align-items:stretch; flex-direction:column; }
      .privacy { text-align:left; } }
  </style>
</head>
<body>
<main>
  <header>
    <div><h1>MLX90640 实时热成像</h1><div class="sub" id="identity">等待设备信息</div></div>
    <div class="status" id="status" role="status" aria-live="polite"><span class="dot"></span><span>连接中</span></div>
  </header>
  <section class="panel" aria-label="实时热阵列">
    <div class="canvas-wrap" id="wrap"><canvas class="smooth" id="heat" width="32" height="24" aria-label="32乘24热成像画面"></canvas><div class="tooltip" id="tip"></div></div>
    <div class="metrics">
      <div class="metric"><div class="label">温度范围</div><div class="value" id="range">—</div></div>
      <div class="metric"><div class="label">平均温度</div><div class="value" id="mean">—</div></div>
      <div class="metric"><div class="label">采集帧率</div><div class="value" id="fps">—</div></div>
      <div class="metric"><div class="label">帧龄</div><div class="value" id="age">—</div></div>
    </div>
    <div class="legend"><span id="lo">低</span><div class="scale" aria-hidden="true"></div><span id="hi">高</span></div>
    <div class="toolbar"><button id="smooth" type="button" aria-pressed="true">平滑显示：开</button><div class="privacy">仅内存保留最新一帧 · 二进制长轮询 · __RENDER_FPS__ FPS 插值渲染</div></div>
  </section>
</main>
<script>
  const PIXELS=768,RENDER_FPS=__RENDER_FPS__,MIN_RENDER_MS=1000/RENDER_FPS;
  const canvas=document.getElementById('heat'),ctx=canvas.getContext('2d'),tip=document.getElementById('tip'),wrap=document.getElementById('wrap');
  const stops=[[0,[23,27,92]],[.18,[32,89,168]],[.38,[21,156,145]],[.58,[143,189,63]],[.76,[244,181,47]],[.9,[235,90,42]],[1,[125,8,40]]];
  let sequence=0,target=null,display=null,from=null,transitionStart=0,transitionMs=16,capturedAt=0,captureFps=0,smoothing=true,lastRender=0;
  const text=(id,value)=>document.getElementById(id).textContent=value;
  const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  function setStatus(kind,label){const node=document.getElementById('status');node.className='status '+kind;node.lastElementChild.textContent=label;}
  function color(t){t=Math.max(0,Math.min(1,t));let a=stops[0],b=stops.at(-1);for(let i=1;i<stops.length;i++){if(t<=stops[i][0]){a=stops[i-1];b=stops[i];break;}}const p=(t-a[0])/(b[0]-a[0]||1);return a[1].map((v,i)=>Math.round(v+(b[1][i]-v)*p));}
  function draw(values){const min=Math.min(...values),max=Math.max(...values),span=Math.max(.01,max-min),image=ctx.createImageData(32,24);values.forEach((value,index)=>{const c=color((value-min)/span),offset=index*4;image.data[offset]=c[0];image.data[offset+1]=c[1];image.data[offset+2]=c[2];image.data[offset+3]=255;});ctx.putImageData(image,0,0);}
  function acceptFrame(buffer,response){if(buffer.byteLength!==PIXELS*2)throw new Error('invalid thermal frame length');const view=new DataView(buffer),values=new Array(PIXELS);for(let i=0;i<PIXELS;i++)values[i]=view.getInt16(i*2,true)/100;const now=performance.now();from=display?display.slice():values.slice();display=display||values.slice();target=values;transitionStart=now;captureFps=Number(response.headers.get('X-Thermal-Capture-FPS')||0);const period=captureFps>0?1000/captureFps:100;transitionMs=Math.min(250,Math.max(16,period*.9));capturedAt=Date.parse(response.headers.get('X-Thermal-Captured-At')||'');sequence=Number(response.headers.get('X-Thermal-Sequence')||sequence);const min=Math.min(...values),max=Math.max(...values),mean=values.reduce((sum,value)=>sum+value,0)/PIXELS;text('range',min.toFixed(1)+'–'+max.toFixed(1)+' °C');text('mean',mean.toFixed(1)+' °C');text('fps',captureFps>0?captureFps.toFixed(1)+' FPS':'采样中');text('lo',min.toFixed(1)+' °C');text('hi',max.toFixed(1)+' °C');setStatus('ready','实况 · 帧 '+sequence);}
  function render(now){requestAnimationFrame(render);if(!target||now-lastRender<MIN_RENDER_MS)return;lastRender=now;const raw=smoothing?Math.min(1,(now-transitionStart)/transitionMs):1,alpha=raw*raw*(3-2*raw);for(let i=0;i<PIXELS;i++)display[i]=from[i]+(target[i]-from[i])*alpha;draw(display);text('age',Number.isFinite(capturedAt)?Math.max(0,Date.now()-capturedAt).toFixed(0)+' ms':'—');}
  async function streamFrames(){while(true){try{const response=await fetch('/frame.bin?after='+sequence,{cache:'no-store'});if(response.status===204)continue;if(!response.ok)throw new Error('frame request failed');acceptFrame(await response.arrayBuffer(),response);}catch(error){setStatus('error','数据流断开');await delay(500);}}}
  async function updateHealth(){try{const response=await fetch('/health',{cache:'no-store'}),data=await response.json();text('identity',data.room_id+' · '+data.device_id);if(data.status!=='ready')setStatus(data.status,data.status==='error'?'读取异常':'连接中');if(data.error)text('identity',data.error);}catch(error){setStatus('error','服务不可达');}setTimeout(updateHealth,1000);}
  wrap.addEventListener('pointermove',event=>{if(!display)return;const rect=canvas.getBoundingClientRect(),x=Math.min(31,Math.max(0,Math.floor((event.clientX-rect.left)/rect.width*32))),y=Math.min(23,Math.max(0,Math.floor((event.clientY-rect.top)/rect.height*24)));tip.textContent=`(${x}, ${y}) ${display[y*32+x].toFixed(1)} °C`;tip.style.display='block';tip.style.left=(event.clientX-rect.left)+'px';tip.style.top=(event.clientY-rect.top)+'px';});
  wrap.addEventListener('pointerleave',()=>tip.style.display='none');document.getElementById('smooth').addEventListener('click',event=>{smoothing=!smoothing;canvas.classList.toggle('smooth',smoothing);event.currentTarget.setAttribute('aria-pressed',String(smoothing));event.currentTarget.textContent='平滑显示：'+(smoothing?'开':'关');});
  requestAnimationFrame(render);updateHealth();streamFrames();
</script>
</body>
</html>""".replace("__RENDER_FPS__", str(render_fps))


def encode_binary_frame(snapshot: Mapping[str, Any]) -> bytes:
    """Encode one validated frame as little-endian centi-degree int16 values."""

    values = snapshot.get("values", ())
    if len(values) != THERMAL_PIXELS:
        raise ValueError("binary thermal frame must contain 768 values")
    encoded = [int(round(float(value) * 100.0)) for value in values]
    if any(value < -32768 or value > 32767 for value in encoded):
        raise ValueError("binary thermal frame value is outside int16 range")
    return struct.pack(f"<{THERMAL_PIXELS}h", *encoded)


def make_handler(
    store: ThermalFrameStore,
    *,
    render_fps: int = 60,
    wait_timeout_s: float = 1.0,
) -> type[BaseHTTPRequestHandler]:
    """Create an HTTP handler bound to one frame store."""

    html = dashboard_html(render_fps=render_fps).encode("utf-8")

    class ThermalRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib HTTP API
            parsed = urlsplit(self.path)
            path = parsed.path
            if path == "/":
                self._send(HTTPStatus.OK, "text/html; charset=utf-8", html)
                return
            if path == "/frame.bin":
                try:
                    after = int(parse_qs(parsed.query).get("after", ["0"])[0])
                    if after < 0:
                        raise ValueError
                except (TypeError, ValueError):
                    self._send(
                        HTTPStatus.BAD_REQUEST,
                        "application/json; charset=utf-8",
                        b'{"error":"invalid_after_sequence"}',
                    )
                    return
                snapshot = store.wait_for_newer(after, timeout_s=wait_timeout_s)
                headers = {
                    "X-Thermal-Sequence": str(snapshot["sequence"]),
                    "X-Thermal-Captured-At": str(snapshot["captured_at"] or ""),
                    "X-Thermal-Capture-FPS": f'{snapshot["capture_fps"]:.3f}',
                    "X-Thermal-Width": str(snapshot["width"]),
                    "X-Thermal-Height": str(snapshot["height"]),
                }
                if (
                    snapshot["status"] != "ready"
                    or int(snapshot["sequence"]) <= after
                ):
                    self._send(
                        HTTPStatus.NO_CONTENT,
                        "application/octet-stream",
                        b"",
                        headers=headers,
                    )
                    return
                self._send(
                    HTTPStatus.OK,
                    "application/octet-stream",
                    encode_binary_frame(snapshot),
                    headers=headers,
                )
                return
            if path in {"/frame", "/health"}:
                snapshot = store.snapshot()
                if path == "/health":
                    snapshot = {
                        "status": snapshot["status"],
                        "sequence": snapshot["sequence"],
                        "captured_at": snapshot["captured_at"],
                        "capture_fps": snapshot["capture_fps"],
                        "room_id": snapshot["room_id"],
                        "device_id": snapshot["device_id"],
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

        def _send(
            self,
            status: HTTPStatus,
            content_type: str,
            body: bytes,
            *,
            headers: Mapping[str, str] | None = None,
        ) -> None:
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
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            if body:
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    LOGGER.debug("viewer client disconnected before response completed")

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
    parser.add_argument("--render-fps", type=int, default=60)
    parser.add_argument("--refresh-ms", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if not 15 <= args.render_fps <= 120:
        parser.error("--render-fps must be between 15 and 120")
    render_fps = args.render_fps
    if args.refresh_ms is not None:
        if not 16 <= args.refresh_ms <= 1000:
            parser.error("--refresh-ms must be between 16 and 1000")
        render_fps = max(15, min(120, round(1000 / args.refresh_ms)))

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s level=%(levelname)s message=%(message)s",
    )
    config = load_config(args.config)
    store = ThermalFrameStore(room_id=config.room_id, device_id=config.device_id)
    capture = ThermalCapture(build_thermal_driver(config), store)
    server = ThreadingHTTPServer(
        (args.host, args.port),
        make_handler(store, render_fps=render_fps),
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
