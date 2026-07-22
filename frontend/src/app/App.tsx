import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  allCandidateIds,
  defaultRequest,
  isRealApi,
  loadDashboardData,
  login as loginUser,
  logout as logoutUser,
  recordRoomSelection,
  register as registerUser,
  saveMyPreferences,
} from "../api/client";
import type {
  DashboardData,
  HistoryPoint,
  OccupancyLevel,
  RecommendationItem,
  RecommendationRequest,
  RoomStatus,
  StudyMode,
  ThermalPreviewResponse,
} from "../types/contracts";

type ViewMode = "student" | "admin";

const labels = {
  quiet: "Quiet study",
  discussion: "Discussion",
  any: "Any mode",
  empty: "Empty",
  low: "Low",
  medium: "Medium",
  high: "High",
  unknown: "Unknown",
  empty_or_low_activity: "Low activity",
  quiet_study_recommended: "Quiet",
  discussion_allowed: "Discussion",
  not_recommended_noisy_or_crowded: "Noisy/crowded",
};

export function App() {
  const [viewMode, setViewMode] = useState<ViewMode>("student");
  const [adminAuthenticated, setAdminAuthenticated] = useState(() => window.sessionStorage.getItem("study-space-admin-auth") === "true");
  const [request, setRequest] = useState<RecommendationRequest>(defaultRequest);
  const [data, setData] = useState<DashboardData | null>(null);
  const [selectedRoomId, setSelectedRoomId] = useState("room_a");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [authBusy, setAuthBusy] = useState(false);
  const [authMessage, setAuthMessage] = useState<string | null>(null);
  const [selectionMessage, setSelectionMessage] = useState<string | null>(null);

  const selectedRoom = data?.rooms.find((room) => room.room_id === selectedRoomId) ?? data?.rooms[0];
  const selectedRecommendation = data?.recommendations.recommendations.find((item) => item.room_id === selectedRoom?.room_id);

  async function refresh(nextRequest = request, options: { selectTopRoom?: boolean } = {}) {
    setLoading(true);
    setError(null);
    try {
      const response = await loadDashboardData(nextRequest);
      setData(response);
      setSelectedRoomId((currentRoomId) => {
        if (options.selectTopRoom) {
          return response.recommendations.recommendations[0]?.room_id ?? response.rooms[0]?.room_id ?? "";
        }
        return response.rooms.some((room) => room.room_id === currentRoomId) ? currentRoomId : (response.rooms[0]?.room_id ?? "");
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dashboard data could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh(request);
    const seconds = Number(import.meta.env.VITE_REFRESH_SECONDS ?? 10);
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh(request);
    }, Math.max(5, seconds) * 1000);
    return () => window.clearInterval(id);
  }, []);

  async function applyRequest(nextRequest: RecommendationRequest) {
    setRequest(nextRequest);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1800);
    try {
      if (isRealApi && data?.authenticated) {
        await saveMyPreferences(nextRequest, data.preferences?.learning_enabled ?? true);
      }
      await refresh(nextRequest, { selectTopRoom: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Preferences could not be saved.");
    }
  }

  async function handleAuth(mode: "login" | "register", username: string, password: string) {
    setAuthBusy(true);
    setAuthMessage(null);
    setError(null);
    try {
      const session = mode === "login" ? await loginUser({ username, password }) : await registerUser({ username, password });
      setAuthMessage(`Signed in as ${session.user.username}.`);
      await refresh(request, { selectTopRoom: true });
    } catch (err) {
      setAuthMessage(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setAuthBusy(false);
    }
  }

  async function handleLogout() {
    setAuthBusy(true);
    setAuthMessage(null);
    try {
      await logoutUser();
      setAuthMessage("Signed out.");
      await refresh(request, { selectTopRoom: true });
    } catch (err) {
      setAuthMessage(err instanceof Error ? err.message : "Sign out failed.");
    } finally {
      setAuthBusy(false);
    }
  }

  async function chooseRoom(roomId: string, source: "recommendation" | "room_detail") {
    setSelectedRoomId(roomId);
    setSelectionMessage(null);
    if (!isRealApi || !data?.authenticated) return;
    try {
      await recordRoomSelection(roomId, source === "recommendation" ? data.recommendations.request_id : null, source);
      setSelectionMessage("Choice saved for preference learning.");
    } catch (err) {
      setSelectionMessage(err instanceof Error ? err.message : "Room choice could not be saved.");
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Privacy-preserving AIoT</p>
          <h1>Study Space Advisor</h1>
          <p className="privacy-line">No RGB camera, no face or identity recognition, no raw voice storage.</p>
        </div>
        <div className="status-stack" aria-live="polite">
          <StatusPill status={data?.backendStatus ?? (error ? "offline" : "degraded")} />
          <span className="muted">Updated {formatTime(data?.lastUpdated)}</span>
          <button className="icon-button" type="button" onClick={() => void refresh()} aria-label="Refresh dashboard" title="Refresh dashboard">
            Refresh
          </button>
        </div>
      </header>
      <nav className="view-switch" aria-label="Dashboard view">
        <button type="button" className={viewMode === "student" ? "active" : ""} onClick={() => setViewMode("student")}>
          Student view
        </button>
        <button type="button" className={viewMode === "admin" ? "active" : ""} onClick={() => setViewMode("admin")}>
          Admin view
        </button>
      </nav>

      {error && data && <Notice tone="danger" text={`Backend connection failed; showing last successful data. ${error}`} />}
      {viewMode === "admin" && data?.recommendations.warnings.length ? <Notice tone="warning" text={data.recommendations.warnings.join(", ")} /> : null}
      {loading && !data ? <Skeleton /> : null}
      {isRealApi && viewMode === "student" ? (
        <SessionPanel
          user={data?.user ?? null}
          busy={authBusy}
          message={authMessage}
          onAuth={handleAuth}
          onLogout={handleLogout}
        />
      ) : null}

      {data && viewMode === "student" ? (
        <div className="workspace">
          <PreferencesPanel request={request} saved={saved} profileLabel={data.authenticated ? "Signed-in profile" : "Anonymous demo profile"} onApply={applyRequest} />
          <section className="recommendation-zone" aria-label="Room recommendations">
            <RecommendationList
              recommendations={data.recommendations.recommendations}
              rooms={data.rooms}
              selectedRoomId={selectedRoom?.room_id ?? ""}
              onSelect={setSelectedRoomId}
            />
            {selectedRoom ? (
              <RoomDetail
                room={selectedRoom}
                recommendation={selectedRecommendation}
                selectionMessage={selectionMessage}
                onChoose={data.authenticated ? (roomId) => void chooseRoom(roomId, selectedRecommendation ? "recommendation" : "room_detail") : undefined}
              />
            ) : (
              <EmptyState />
            )}
          </section>
        </div>
      ) : null}
      {data && viewMode === "admin" && !adminAuthenticated ? <AdminLogin onLogin={() => setAdminAuthenticated(true)} /> : null}
      {data && viewMode === "admin" && adminAuthenticated ? (
        <AdminDashboard
          data={data}
          onSelectRoom={setSelectedRoomId}
          onOpenStudent={() => setViewMode("student")}
          onSignOut={() => {
            window.sessionStorage.removeItem("study-space-admin-auth");
            setAdminAuthenticated(false);
          }}
        />
      ) : null}
    </main>
  );
}

function SessionPanel({
  user,
  busy,
  message,
  onAuth,
  onLogout,
}: {
  user: DashboardData["user"];
  busy: boolean;
  message: string | null;
  onAuth: (mode: "login" | "register", username: string, password: string) => Promise<void>;
  onLogout: () => Promise<void>;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitAuth("login");
  }

  async function submitAuth(mode: "login" | "register") {
    await onAuth(mode, username.trim(), password);
  }

  return (
    <section className="session-panel" aria-label="Student account">
      <div>
        <p className="eyebrow">Student account</p>
        <h2>{user ? `Welcome, ${user.username}` : "Sign in for learned preferences"}</h2>
        <p className="muted">The backend now stores only local account credentials, preference settings, and room choices for recommendation learning.</p>
      </div>
      {user ? (
        <div className="session-actions">
          <span className="save-state">Session active</span>
          <button type="button" disabled={busy} onClick={() => void onLogout()}>
            Sign out
          </button>
        </div>
      ) : (
        <form className="session-form" onSubmit={(event) => void submit(event)}>
          <label>
            Username
            <input value={username} autoComplete="username" onChange={(event) => setUsername(event.currentTarget.value)} placeholder="studyuser" />
          </label>
          <label>
            Password
            <input value={password} autoComplete="current-password" onChange={(event) => setPassword(event.currentTarget.value)} placeholder="10+ characters" type="password" />
          </label>
          <div className="button-row">
            <button type="submit" className="primary" disabled={busy}>
              Sign in
            </button>
            <button type="button" disabled={busy} onClick={() => void submitAuth("register")}>
              Register
            </button>
          </div>
        </form>
      )}
      {message ? <p className="inline-note">{message}</p> : null}
    </section>
  );
}

function PreferencesPanel({
  request,
  saved,
  profileLabel,
  onApply,
}: {
  request: RecommendationRequest;
  saved: boolean;
  profileLabel: string;
  onApply: (request: RecommendationRequest) => void;
}) {
  const [draft, setDraft] = useState(request);
  const hasLocation = false;

  function setMode(study_mode: StudyMode) {
    setDraft({ ...draft, study_mode });
  }

  function setPreference(key: keyof RecommendationRequest["preferences"], value: number) {
    setDraft({ ...draft, preferences: { ...draft.preferences, [key]: value } });
  }

  function reset() {
    setDraft({ ...defaultRequest, candidate_room_ids: allCandidateIds() });
  }

  return (
    <aside className="preferences" aria-label="Study preferences">
      <div className="panel-heading">
        <h2>Preferences</h2>
        <span className="save-state">{saved ? "Saved" : profileLabel}</span>
      </div>
      <fieldset className="segmented">
        <legend>Study mode</legend>
        {(["quiet", "discussion", "any"] as StudyMode[]).map((mode) => (
          <button key={mode} type="button" className={draft.study_mode === mode ? "active" : ""} onClick={() => setMode(mode)}>
            {labels[mode]}
          </button>
        ))}
      </fieldset>
      <Slider label="Quiet priority" value={draft.preferences.quiet_priority} onChange={(value) => setPreference("quiet_priority", value)} />
      <Slider label="Low occupancy" value={draft.preferences.low_occupancy_priority} onChange={(value) => setPreference("low_occupancy_priority", value)} />
      <Slider label="Brightness" value={draft.preferences.brightness_priority} onChange={(value) => setPreference("brightness_priority", value)} />
      <Slider label="Temperature and humidity" value={draft.preferences.comfort_priority} onChange={(value) => setPreference("comfort_priority", value)} />
      <Slider label="Distance" value={draft.preferences.distance_priority} disabled={!hasLocation} onChange={(value) => setPreference("distance_priority", value)} />
      {!hasLocation ? <p className="inline-note">Distance is disabled because room coordinates are not available in the current backend response.</p> : null}
      <div className="button-row">
        <button type="button" className="primary" onClick={() => onApply(draft)}>
          Apply preferences
        </button>
        <button type="button" onClick={reset}>
          Defaults
        </button>
      </div>
    </aside>
  );
}

function Slider({ label, value, disabled, onChange }: { label: string; value: number; disabled?: boolean; onChange: (value: number) => void }) {
  return (
    <label className="slider-row">
      <span>
        {label}
        <strong>{value.toFixed(1)}</strong>
      </span>
      <input disabled={disabled} type="range" min="0" max="1" step="0.1" value={value} onChange={(event) => onChange(Number(event.currentTarget.value))} />
    </label>
  );
}

function RecommendationList({
  recommendations,
  rooms,
  selectedRoomId,
  onSelect,
}: {
  recommendations: RecommendationItem[];
  rooms: RoomStatus[];
  selectedRoomId: string;
  onSelect: (roomId: string) => void;
}) {
  if (!recommendations.length) return <EmptyState />;
  const roomMap = new Map(rooms.map((room) => [room.room_id, room]));
  const [first, ...rest] = recommendations;
  return (
    <section className="recommendations">
      <h2>Recommendations</h2>
      <FeaturedRecommendation item={first} room={roomMap.get(first.room_id)} selected={selectedRoomId === first.room_id} onSelect={onSelect} />
      <div className="compact-list">
        {rest.map((item) => (
          <RecommendationRow key={item.room_id} item={item} room={roomMap.get(item.room_id)} selected={selectedRoomId === item.room_id} onSelect={onSelect} />
        ))}
      </div>
    </section>
  );
}

function FeaturedRecommendation({ item, room, selected, onSelect }: { item: RecommendationItem; room?: RoomStatus; selected: boolean; onSelect: (roomId: string) => void }) {
  return (
    <button className={`featured ${selected ? "selected" : ""}`} type="button" onClick={() => onSelect(item.room_id)}>
      <span className="rank">#{item.rank}</span>
      <span>
        <strong>{room?.name ?? item.room_id}</strong>
        <small>{room?.location ?? "Unknown location"}</small>
      </span>
      <Score value={item.score} />
      <StateBadges room={room} item={item} />
      <p>{item.explanation}</p>
    </button>
  );
}

function RecommendationRow({ item, room, selected, onSelect }: { item: RecommendationItem; room?: RoomStatus; selected: boolean; onSelect: (roomId: string) => void }) {
  return (
    <button className={`rec-row ${selected ? "selected" : ""}`} type="button" onClick={() => onSelect(item.room_id)}>
      <span className="rank">#{item.rank}</span>
      <span className="row-title">
        <strong>{room?.name ?? item.room_id}</strong>
        <small>{labels[item.occupancy_level]} occupancy, 30m {labels[item.forecast_30m]}</small>
      </span>
      <Score value={item.score} />
      <StateBadges room={room} item={item} />
    </button>
  );
}

function RoomDetail({
  room,
  recommendation,
  selectionMessage,
  onChoose,
}: {
  room: RoomStatus;
  recommendation?: RecommendationItem;
  selectionMessage?: string | null;
  onChoose?: (roomId: string) => void;
}) {
  const forecastLabel = recommendation ? labels[recommendation.forecast_30m] : "Unknown";
  const visibleReasons = recommendation?.reasons.filter((reason) => !reason.toLowerCase().includes("sensor") && !reason.toLowerCase().includes("confidence")).slice(0, 3) ?? [];
  return (
    <section className="detail" aria-label={`${room.name} detail`}>
      <div className="detail-heading">
        <div>
          <h2>{room.name}</h2>
          <p className="muted">{room.location ?? "Unknown location"}</p>
        </div>
        <StateBadges room={room} item={recommendation} />
      </div>
      <div className="metric-grid">
        <Metric label="Vibe" value={labels[room.room_state]} />
        <Metric label="Crowd" value={labels[room.occupancy_level]} />
        <Metric label="Next 30 min" value={forecastLabel} />
      </div>
      {visibleReasons.length ? (
        <div className="reason-band">
          {visibleReasons.map((reason) => (
            <span key={reason}>{reason}</span>
          ))}
        </div>
      ) : null}
      {room.is_stale ? <Notice tone="warning" text="Live signals for this room may be delayed, so check the space before walking over." /> : null}
      {onChoose ? (
        <div className="selection-action">
          <button type="button" className="primary" onClick={() => onChoose(room.room_id)}>
            Choose this room
          </button>
          {selectionMessage ? <span className="inline-note">{selectionMessage}</span> : null}
        </div>
      ) : null}
      <PrivacyPanel />
    </section>
  );
}

function AdminLogin({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (username.trim() === "admin" && password === "admin123") {
      window.sessionStorage.setItem("study-space-admin-auth", "true");
      setMessage(null);
      onLogin();
      return;
    }
    setMessage("Invalid demo credentials. Try admin / admin123.");
  }

  return (
    <section className="admin-login" aria-label="Admin login">
      <div>
        <p className="eyebrow">Admin access</p>
        <h2>Sign in to operations console</h2>
        <p className="muted">Demo credentials protect the admin view during testing. Production auth should be handled by the backend.</p>
      </div>
      <form onSubmit={submit}>
        <label>
          Username
          <input value={username} autoComplete="username" onChange={(event) => setUsername(event.currentTarget.value)} placeholder="admin" />
        </label>
        <label>
          Password
          <input value={password} autoComplete="current-password" onChange={(event) => setPassword(event.currentTarget.value)} placeholder="admin123" type="password" />
        </label>
        {message ? (
          <p className="login-error" role="alert">
            {message}
          </p>
        ) : (
          <p className="inline-note">Demo access: admin / admin123</p>
        )}
        <button type="submit" className="primary">
          Sign in
        </button>
      </form>
    </section>
  );
}

function AdminDashboard({
  data,
  onSelectRoom,
  onOpenStudent,
  onSignOut,
}: {
  data: DashboardData;
  onSelectRoom: (roomId: string) => void;
  onOpenStudent: () => void;
  onSignOut: () => void;
}) {
  const rooms = data.rooms;
  const staleRooms = rooms.filter((room) => room.is_stale);
  const offlineSensors = rooms.flatMap((room) => Object.entries(room.sensor_health).filter(([, health]) => health === "offline").map(([name]) => `${room.name} ${name}`));
  const degradedSensors = rooms.flatMap((room) => Object.entries(room.sensor_health).filter(([, health]) => health === "degraded").map(([name]) => `${room.name} ${name}`));
  const lowConfidence = rooms.filter((room) => (room.confidence ?? 0) < 0.55);
  const averageConfidence = rooms.length ? Math.round((rooms.reduce((sum, room) => sum + (room.confidence ?? 0), 0) / rooms.length) * 100) : 0;
  const roomWithIssues = rooms.filter((room) => room.is_stale || room.warnings.length || Object.values(room.sensor_health).some((health) => health === "degraded" || health === "offline")).length;
  const alerts = buildAdminAlerts(rooms);

  return (
    <section className="admin-dashboard" aria-label="Admin operations dashboard">
      <div className="admin-hero">
        <div>
          <p className="eyebrow">Operations console</p>
          <h2>Space health at a glance</h2>
          <p className="muted">Monitor room availability, sensor health, stale data, and privacy-safe data quality before students see recommendations.</p>
        </div>
        <div className="admin-actions">
          <StatusPill status={data.backendStatus} />
          <button type="button" className="primary" onClick={onOpenStudent}>
            Open student view
          </button>
          <button type="button" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      </div>

      <div className="admin-kpis">
        <AdminKpi label="Rooms online" value={`${rooms.length - staleRooms.length}/${rooms.length}`} tone="ok" detail={`${roomWithIssues} need attention`} />
        <AdminKpi label="Avg confidence" value={`${averageConfidence}%`} tone={averageConfidence >= 70 ? "ok" : "warning"} detail={`${lowConfidence.length} low-confidence rooms`} />
        <AdminKpi label="Sensor issues" value={`${offlineSensors.length + degradedSensors.length}`} tone={offlineSensors.length ? "danger" : degradedSensors.length ? "warning" : "ok"} detail={`${offlineSensors.length} offline, ${degradedSensors.length} degraded`} />
        <AdminKpi label="Stale rooms" value={`${staleRooms.length}`} tone={staleRooms.length ? "warning" : "ok"} detail="Freshness guard for recommendations" />
      </div>

      <div className="admin-grid">
        <section className="admin-panel room-ops">
          <div className="panel-heading">
            <h3>Room operations</h3>
            <span className="muted">Live aggregate state</span>
          </div>
          <div className="admin-table" role="table" aria-label="Room operations table">
            <div className="admin-row admin-row-head" role="row">
              <span>Room</span>
              <span>State</span>
              <span>Confidence</span>
              <span>Data age</span>
              <span>Action</span>
            </div>
            {rooms.map((room) => (
              <div className="admin-row" role="row" key={room.room_id}>
                <span>
                  <strong>{room.name}</strong>
                  <small>{room.location ?? "Unknown location"}</small>
                </span>
                <span>
                  <Badge tone={toneForOccupancy(room.occupancy_level)} text={labels[room.room_state]} />
                </span>
                <span>{Math.round((room.confidence ?? 0) * 100)}%</span>
                <span>{room.data_age_seconds == null ? "No data" : `${Math.round(room.data_age_seconds)}s`}</span>
                <span>
                  <button
                    type="button"
                    onClick={() => {
                      onSelectRoom(room.room_id);
                      onOpenStudent();
                    }}
                  >
                    Inspect
                  </button>
                </span>
              </div>
            ))}
          </div>
        </section>

        <section className="admin-panel">
          <div className="panel-heading">
            <h3>Sensor matrix</h3>
            <span className="muted">Per-room device health</span>
          </div>
          <div className="sensor-matrix">
            {rooms.map((room) => (
              <div className="sensor-room" key={room.room_id}>
                <strong>{room.name}</strong>
                <div>
                  {Object.entries(room.sensor_health).map(([sensor, health]) => (
                    <span className={`sensor-chip ${health}`} key={`${room.room_id}-${sensor}`}>
                      {sensor}
                      <small>{health}</small>
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="admin-panel">
          <div className="panel-heading">
            <h3>Alert queue</h3>
            <span className="muted">{alerts.length} active</span>
          </div>
          <div className="alert-list">
            {alerts.map((alert) => (
              <div className={`alert-item ${alert.tone}`} key={alert.title}>
                <span>{alert.tone.toUpperCase()}</span>
                <strong>{alert.title}</strong>
                <p>{alert.detail}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="admin-panel">
          <div className="panel-heading">
            <h3>Privacy and data quality</h3>
            <span className="muted">Module 4 guardrails</span>
          </div>
          <div className="quality-list">
            <QualityItem label="Raw RGB camera" value="Disabled" tone="ok" />
            <QualityItem label="Face or identity recognition" value="Not used" tone="ok" />
            <QualityItem label="Raw voice storage" value="Blocked" tone="ok" />
            <QualityItem label="LLM explanation fallback" value={data.recommendations.warnings.includes("LLM_TEMPLATE_FALLBACK") ? "Template active" : "Normal"} tone="warning" />
            <QualityItem label="Recommendation warnings" value={`${data.recommendations.warnings.length}`} tone={data.recommendations.warnings.length ? "warning" : "ok"} />
          </div>
        </section>
      </div>
    </section>
  );
}

function AdminKpi({ label, value, detail, tone }: { label: string; value: string; detail: string; tone: "ok" | "warning" | "danger" }) {
  return (
    <article className={`admin-kpi ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <p>{detail}</p>
    </article>
  );
}

function QualityItem({ label, value, tone }: { label: string; value: string; tone: "ok" | "warning" | "danger" }) {
  return (
    <div className="quality-item">
      <span>
        <strong>{label}</strong>
        <small>{value}</small>
      </span>
      <Badge tone={tone} text={tone === "ok" ? "OK" : tone === "warning" ? "Check" : "Critical"} />
    </div>
  );
}

function buildAdminAlerts(rooms: RoomStatus[]) {
  const alerts = rooms.flatMap((room) => {
    const items: Array<{ tone: "warning" | "danger"; title: string; detail: string }> = [];
    if (room.is_stale) items.push({ tone: "warning", title: `${room.name} data is stale`, detail: "Recommendations will apply stale-data penalties until fresh observations arrive." });
    if ((room.confidence ?? 0) < 0.55) items.push({ tone: "warning", title: `${room.name} confidence is low`, detail: "Review model inputs before presenting this room as a strong suggestion." });
    Object.entries(room.sensor_health).forEach(([sensor, health]) => {
      if (health === "offline") items.push({ tone: "danger", title: `${room.name} ${sensor} offline`, detail: "Maintenance should inspect connectivity or configuration." });
      if (health === "degraded") items.push({ tone: "warning", title: `${room.name} ${sensor} degraded`, detail: "Data is usable but recommendation confidence may be reduced." });
    });
    return items;
  });
  return alerts.length ? alerts : [{ tone: "warning" as const, title: "No active incidents", detail: "All configured sensors are currently reporting normally." }];
}

function TrendChart({ points }: { points: HistoryPoint[] }) {
  const values = points.map((point) => point.occupancy_mean ?? 0);
  const path = values
    .map((value, index) => {
      const x = 8 + (index / Math.max(1, values.length - 1)) * 284;
      const y = 112 - (value / 3) * 96;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <section className="trend" aria-label="Occupancy history">
      <div className="panel-heading">
        <h3>History and forecast</h3>
        <span className="muted">Occupancy level, last hour</span>
      </div>
      {points.length ? (
        <svg viewBox="0 0 300 130" role="img" aria-label="Line chart of occupancy history">
          <path d="M8 112 H292" className="axis" />
          <path d="M8 16 V112" className="axis" />
          <path d={path} className="trend-line" />
          {values.map((value, index) => (
            <circle key={`${index}-${value}`} cx={8 + (index / Math.max(1, values.length - 1)) * 284} cy={112 - (value / 3) * 96} r="3.5" />
          ))}
        </svg>
      ) : (
        <p className="empty">No history available.</p>
      )}
    </section>
  );
}

function ThermalPreview({ preview }: { preview?: ThermalPreviewResponse }) {
  const cells = useMemo(() => preview?.values?.slice(0, 32 * 24) ?? [], [preview]);
  return (
    <section className="thermal" aria-label="Thermal preview">
      <div className="panel-heading">
        <h3>Thermal preview</h3>
        <span className="muted">32 x 24 normalized</span>
      </div>
      {preview?.available && cells.length ? (
        <div className="heatmap" role="img" aria-label="Low resolution non-camera thermal distribution preview">
          {cells.map((value, index) => (
            <span key={index} style={{ backgroundColor: heatColor(value) }} />
          ))}
        </div>
      ) : (
        <p className="empty">Unavailable: {preview?.unavailable_reason ?? "not_available"}</p>
      )}
      <p className="inline-note">Non-camera image for current overall heat distribution only; not saved as history.</p>
    </section>
  );
}

function PrivacyPanel() {
  return (
    <section className="privacy-panel">
      <h3>Privacy</h3>
      <ul>
        <li>No RGB camera.</li>
        <li>No face or identity recognition.</li>
        <li>No raw voice storage.</li>
        <li>Dashboard shows aggregate state and occupancy level.</li>
      </ul>
    </section>
  );
}

function StateBadges({ room, item }: { room?: RoomStatus; item?: RecommendationItem }) {
  return (
    <span className="badges">
      {room ? <Badge tone={toneForOccupancy(room.occupancy_level)} text={labels[room.room_state]} /> : null}
      {item ? <Badge tone={toneForOccupancy(item.forecast_30m)} text={`30m ${labels[item.forecast_30m]}`} /> : null}
    </span>
  );
}

function Badge({ text, tone }: { text: string; tone: "ok" | "info" | "warning" | "danger" }) {
  return <span className={`badge ${tone}`}>{text}</span>;
}

function Score({ value }: { value: number }) {
  const label = value >= 80 ? "Best" : value >= 50 ? "Good" : "Fair";
  return (
    <span className="score" aria-label={`Recommendation fit ${label}`}>
      {label}
    </span>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusPill({ status }: { status: "ok" | "degraded" | "offline" }) {
  const text = status === "ok" ? "Backend connected" : status === "degraded" ? "Mock/fallback active" : "Offline";
  return <span className={`status-pill ${status}`}>{text}</span>;
}

function Notice({ tone, text }: { tone: "warning" | "danger"; text: string }) {
  return (
    <div className={`notice ${tone}`} role="status">
      {text}
    </div>
  );
}

function Skeleton() {
  return (
    <div className="skeleton" aria-label="Loading dashboard">
      <span />
      <span />
      <span />
    </div>
  );
}

function EmptyState() {
  return <p className="empty">No active rooms are available for recommendation.</p>;
}

function toneForOccupancy(level: OccupancyLevel) {
  if (level === "empty" || level === "low") return "ok" as const;
  if (level === "medium") return "warning" as const;
  if (level === "high") return "danger" as const;
  return "info" as const;
}

function heatColor(value: number) {
  const clamped = Math.max(0, Math.min(1, value));
  const hue = 205 - clamped * 175;
  const light = 92 - clamped * 42;
  return `hsl(${hue} 80% ${light}%)`;
}

function formatTime(value?: string) {
  if (!value) return "pending";
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(value));
}
