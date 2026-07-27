import { useEffect, useMemo, useRef, useState } from "react";
import { isRealApi, loadLiveSensorSnapshot, loadRoomStatuses } from "../api/client";
import type { RoomStatus, ThermalPreviewResponse } from "../types/contracts";

type DisplayMode = "smooth" | "pixels";

const COLOR_STOPS = [
  { at: 0, color: [5, 10, 25] },
  { at: 0.16, color: [24, 45, 133] },
  { at: 0.34, color: [16, 170, 205] },
  { at: 0.53, color: [62, 218, 132] },
  { at: 0.7, color: [247, 216, 67] },
  { at: 0.86, color: [255, 91, 40] },
  { at: 1, color: [255, 244, 210] },
] as const;

export function ThermalMonitorPage() {
  const query = useMemo(() => new URLSearchParams(window.location.search), []);
  const [rooms, setRooms] = useState<RoomStatus[]>([]);
  const [roomId, setRoomId] = useState(query.get("room") ?? "room_a");
  const [preview, setPreview] = useState<ThermalPreviewResponse | null>(null);
  const [room, setRoom] = useState<RoomStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [displayMode, setDisplayMode] = useState<DisplayMode>("smooth");
  const [showGrid, setShowGrid] = useState(false);
  const [frozen, setFrozen] = useState(false);
  const stageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    loadRoomStatuses()
      .then((nextRooms) => {
        if (cancelled) return;
        setRooms(nextRooms);
        if (!nextRooms.some((candidate) => candidate.room_id === roomId)) {
          setRoomId(nextRooms[0]?.room_id ?? "");
        }
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Room list could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!roomId || frozen) return;
    let stopped = false;
    let timer: number | undefined;
    const configuredMs = Number(import.meta.env.VITE_LIVE_SENSOR_POLL_MS ?? 1000);
    const pollMs = Number.isFinite(configuredMs) ? Math.max(500, configuredMs) : 1000;

    async function poll() {
      try {
        const next = await loadLiveSensorSnapshot(roomId);
        if (stopped) return;
        if (next.room.is_stale || !next.thermal_preview.available) {
          setPreview(null);
          setRoom(next.room);
          setError(next.room.is_stale ? "The room data is stale. Waiting for a current thermal frame." : `Thermal preview unavailable: ${next.thermal_preview.unavailable_reason ?? "not_available"}.`);
        } else {
          setPreview(next.thermal_preview);
          setRoom(next.room);
          setError(null);
        }
      } catch (reason) {
        if (!stopped) {
          setPreview(null);
          setError(reason instanceof Error ? reason.message : "The thermal stream could not be loaded.");
        }
      } finally {
        if (!stopped) {
          setLoading(false);
          timer = window.setTimeout(() => void poll(), pollMs);
        }
      }
    }

    setLoading(true);
    void poll();
    return () => {
      stopped = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [roomId, frozen]);

  const stats = useMemo(() => thermalStats(preview), [preview]);
  const selectedName = room?.name ?? rooms.find((candidate) => candidate.room_id === roomId)?.name ?? roomId;

  function selectRoom(nextRoomId: string) {
    setRoomId(nextRoomId);
    setPreview(null);
    setError(null);
    const nextQuery = new URLSearchParams(window.location.search);
    nextQuery.set("room", nextRoomId);
    nextQuery.set("mode", isRealApi ? "api" : "mock");
    window.history.replaceState(null, "", `/thermal?${nextQuery.toString()}`);
  }

  async function openFullscreen() {
    if (stageRef.current?.requestFullscreen) await stageRef.current.requestFullscreen();
  }

  return (
    <main className="thermal-monitor-shell">
      <header className="thermal-monitor-header">
        <div className="thermal-monitor-brand">
          <a href={isRealApi ? "/?mode=api" : "/?mode=mock"} aria-label="Back to Study Space Advisor">
            ← Dashboard
          </a>
          <div>
            <p>Privacy-safe sensor view</p>
            <h1>Live thermal monitor</h1>
          </div>
        </div>
        <div className="thermal-monitor-status" aria-live="polite">
          <span className={`thermal-live-dot ${error ? "offline" : frozen ? "frozen" : "live"}`} />
          <strong>{error ? "Waiting for data" : frozen ? "Frame frozen" : "Live"}</strong>
          <span>{preview?.captured_at ? formatTimestamp(preview.captured_at) : "No current frame"}</span>
        </div>
      </header>

      <section className="thermal-monitor-toolbar" aria-label="Thermal monitor controls">
        <label>
          Room
          <select value={roomId} onChange={(event) => selectRoom(event.currentTarget.value)}>
            {rooms.length ? (
              rooms.map((candidate) => (
                <option key={candidate.room_id} value={candidate.room_id}>
                  {candidate.name}
                </option>
              ))
            ) : (
              <option value={roomId}>{selectedName || "Loading rooms"}</option>
            )}
          </select>
        </label>
        <div className="thermal-control-group" aria-label="Display mode">
          <button type="button" className={displayMode === "smooth" ? "active" : ""} onClick={() => setDisplayMode("smooth")}>
            Smooth
          </button>
          <button type="button" className={displayMode === "pixels" ? "active" : ""} onClick={() => setDisplayMode("pixels")}>
            Sensor pixels
          </button>
        </div>
        <button type="button" className={showGrid ? "active" : ""} aria-pressed={showGrid} onClick={() => setShowGrid((current) => !current)}>
          Grid
        </button>
        <button type="button" className={frozen ? "active" : ""} aria-pressed={frozen} onClick={() => setFrozen((current) => !current)}>
          {frozen ? "Resume" : "Freeze"}
        </button>
        <button type="button" onClick={() => void openFullscreen()}>
          Full screen
        </button>
      </section>

      <section className="thermal-monitor-workspace">
        <div className="thermal-stage" ref={stageRef}>
          {preview?.available && preview.values?.length ? (
            <ThermalCanvas preview={preview} mode={displayMode} showGrid={showGrid} />
          ) : (
            <div className="thermal-monitor-empty" role="status">
              <span>{loading ? "Connecting" : "No current frame"}</span>
              <strong>{loading ? "Opening the thermal stream…" : error ?? "The thermal preview is unavailable."}</strong>
              <p>Old frames are not shown as live data.</p>
            </div>
          )}
          {preview?.available ? (
            <div className="thermal-stage-overlay">
              <span>{selectedName}</span>
              <span>{preview.width} × {preview.height} source</span>
            </div>
          ) : null}
        </div>

        <aside className="thermal-monitor-inspector" aria-label="Thermal frame details">
          <div>
            <span>Relative peak</span>
            <strong>{stats ? `${(stats.max * 100).toFixed(1)}%` : "—"}</strong>
          </div>
          <div>
            <span>Relative mean</span>
            <strong>{stats ? `${(stats.mean * 100).toFixed(1)}%` : "—"}</strong>
          </div>
          <div>
            <span>Hot zone</span>
            <strong>{stats ? `C${stats.column + 1} · R${stats.row + 1}` : "—"}</strong>
          </div>
          <div>
            <span>Thermal health</span>
            <strong>{room?.sensor_health.thermal ?? "unknown"}</strong>
          </div>
          <div className="thermal-scale" aria-label="Relative thermal color scale">
            <span>Relative intensity</span>
            <div>
              <i />
              <span><b>100%</b><b>50%</b><b>0%</b></span>
            </div>
          </div>
          <p>
            Smooth mode interpolates the same 32 × 24 values for easier viewing; it does not create additional sensor detail.
          </p>
        </aside>
      </section>

      <footer className="thermal-monitor-footer">
        <strong>MLX90640 low-resolution thermal array</strong>
        <span>No RGB image · no face or identity recognition · normalized relative heat only · frame is not stored as history</span>
      </footer>
    </main>
  );
}

function ThermalCanvas({
  preview,
  mode,
  showGrid,
}: {
  preview: ThermalPreviewResponse;
  mode: DisplayMode;
  showGrid: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const values = preview.values;
    const sourceWidth = preview.width;
    const sourceHeight = preview.height;
    if (!canvas || !values || !sourceWidth || !sourceHeight) return;

    const render = () => {
      const context = canvas.getContext("2d");
      if (!context) return;
      const bounds = canvas.getBoundingClientRect();
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.round(bounds.width * pixelRatio));
      canvas.height = Math.max(1, Math.round(bounds.height * pixelRatio));

      const source = document.createElement("canvas");
      source.width = sourceWidth;
      source.height = sourceHeight;
      const sourceContext = source.getContext("2d");
      if (!sourceContext) return;
      const image = sourceContext.createImageData(sourceWidth, sourceHeight);
      values.slice(0, sourceWidth * sourceHeight).forEach((value, index) => {
        const [red, green, blue] = colorForValue(value);
        image.data[index * 4] = red;
        image.data[index * 4 + 1] = green;
        image.data[index * 4 + 2] = blue;
        image.data[index * 4 + 3] = 255;
      });
      sourceContext.putImageData(image, 0, 0);

      context.clearRect(0, 0, canvas.width, canvas.height);
      context.imageSmoothingEnabled = mode === "smooth";
      context.imageSmoothingQuality = "high";
      context.drawImage(source, 0, 0, canvas.width, canvas.height);

      if (showGrid) {
        context.strokeStyle = "rgba(255,255,255,0.18)";
        context.lineWidth = Math.max(1, pixelRatio * 0.6);
        for (let column = 1; column < sourceWidth; column += 1) {
          const x = (column / sourceWidth) * canvas.width;
          context.beginPath();
          context.moveTo(x, 0);
          context.lineTo(x, canvas.height);
          context.stroke();
        }
        for (let row = 1; row < sourceHeight; row += 1) {
          const y = (row / sourceHeight) * canvas.height;
          context.beginPath();
          context.moveTo(0, y);
          context.lineTo(canvas.width, y);
          context.stroke();
        }
      }
    };

    render();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(render);
    observer?.observe(canvas);
    return () => observer?.disconnect();
  }, [preview, mode, showGrid]);

  return (
    <canvas
      className={`thermal-monitor-canvas ${mode}`}
      ref={canvasRef}
      role="img"
      aria-label={`Live ${preview.width} by ${preview.height} normalized non-camera thermal distribution`}
    />
  );
}

function thermalStats(preview: ThermalPreviewResponse | null) {
  const values = preview?.values;
  const width = preview?.width;
  if (!values?.length || !width) return null;
  let max = -Infinity;
  let maxIndex = 0;
  let total = 0;
  values.forEach((value, index) => {
    const finite = Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0;
    total += finite;
    if (finite > max) {
      max = finite;
      maxIndex = index;
    }
  });
  return {
    max,
    mean: total / values.length,
    column: maxIndex % width,
    row: Math.floor(maxIndex / width),
  };
}

function colorForValue(value: number): [number, number, number] {
  const clamped = Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0;
  const upperIndex = COLOR_STOPS.findIndex((stop) => stop.at >= clamped);
  if (upperIndex <= 0) return [...COLOR_STOPS[0].color];
  const lower = COLOR_STOPS[upperIndex - 1];
  const upper = COLOR_STOPS[upperIndex];
  const progress = (clamped - lower.at) / (upper.at - lower.at);
  return lower.color.map((channel, index) => Math.round(channel + (upper.color[index] - channel) * progress)) as [number, number, number];
}

function formatTimestamp(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    fractionalSecondDigits: 1,
  }).format(new Date(value));
}
