import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  allCandidateIds,
  defaultRequest,
  deleteMe,
  deleteRoomSelections,
  isRealApi,
  loadDashboardData,
  loadLiveSensorSnapshot,
  loadSoundPreview,
  login as loginUser,
  logout as logoutUser,
  recordRoomSelection,
  register as registerUser,
  resetLearnedPreferences,
  saveMyPreferences,
} from "../api/client";
import type {
  DashboardData,
  HistoryPoint,
  LiveSensorSnapshotResponse,
  OccupancyLevel,
  RecommendationItem,
  RecommendationRequest,
  RoomStatus,
  SoundPreviewResponse,
  StudyMode,
  ThermalPreviewResponse,
} from "../types/contracts";

type ViewMode = "student" | "admin";
type FailedSelection = {
  id: string;
  roomId: string;
  roomName: string;
  source: "recommendation" | "room_detail";
  recommendationRequestId: string | null;
  message: string;
};

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
  const [liveSnapshot, setLiveSnapshot] = useState<LiveSensorSnapshotResponse | null>(null);
  const [soundPreview, setSoundPreview] = useState<SoundPreviewResponse | null>(null);
  const [liveSensorError, setLiveSensorError] = useState<string | null>(null);
  const [outbox, setOutbox] = useState<FailedSelection[]>([]);

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

  useEffect(() => {
    setLiveSnapshot(null);
    setSoundPreview(null);
    setLiveSensorError(null);
    if (!isRealApi || !selectedRoomId) return;

    let stopped = false;
    let timer: number | undefined;
    const configuredMs = Number(import.meta.env.VITE_LIVE_SENSOR_POLL_MS ?? 1000);
    const pollMs = Number.isFinite(configuredMs) ? Math.max(500, configuredMs) : 1000;

    async function pollLiveSensors() {
      try {
        const next = await loadLiveSensorSnapshot(selectedRoomId);
        if (stopped) return;
        if (next.room.is_stale) {
          setLiveSnapshot(null);
          setSoundPreview(null);
          setLiveSensorError("Live sensor data is stale. Waiting for a new Raspberry Pi observation.");
        } else {
          setLiveSnapshot(next);
          setSoundPreview(next.sound_preview);
          setLiveSensorError(null);
        }
      } catch (err) {
        if (stopped) return;
        setLiveSnapshot(null);
        setSoundPreview(null);
        setLiveSensorError(err instanceof Error ? err.message : "Live sensor data could not be loaded.");
      } finally {
        if (!stopped) timer = window.setTimeout(() => void pollLiveSensors(), pollMs);
      }
    }

    void pollLiveSensors();
    return () => {
      stopped = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [selectedRoomId]);

  useEffect(() => {
    if (!isRealApi || !selectedRoomId) return;

    let stopped = false;
    let timer: number | undefined;
    const configuredMs = Number(import.meta.env.VITE_SOUND_POLL_MS ?? 250);
    const pollMs = Number.isFinite(configuredMs) ? Math.max(100, configuredMs) : 250;

    async function pollSound() {
      try {
        const next = await loadSoundPreview(selectedRoomId);
        if (!stopped) setSoundPreview(next);
      } catch {
        if (!stopped) setSoundPreview(null);
      } finally {
        if (!stopped) timer = window.setTimeout(() => void pollSound(), pollMs);
      }
    }

    void pollSound();
    return () => {
      stopped = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [selectedRoomId]);

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

  async function handleLearningToggle(enabled: boolean) {
    if (!data?.authenticated) return;
    setAuthBusy(true);
    try {
      await saveMyPreferences(request, enabled);
      setAuthMessage(enabled ? "Preference learning enabled." : "Preference learning paused.");
      await refresh(request);
    } catch (err) {
      setAuthMessage(err instanceof Error ? err.message : "Learning setting could not be saved.");
    } finally {
      setAuthBusy(false);
    }
  }

  async function handleResetLearned() {
    setAuthBusy(true);
    try {
      await resetLearnedPreferences();
      setAuthMessage("Learned preference values reset.");
      await refresh(request);
    } catch (err) {
      setAuthMessage(err instanceof Error ? err.message : "Learned preferences could not be reset.");
    } finally {
      setAuthBusy(false);
    }
  }

  async function handleDeleteSelections() {
    setAuthBusy(true);
    try {
      await deleteRoomSelections();
      setAuthMessage("Room selection history cleared.");
      await refresh(request);
    } catch (err) {
      setAuthMessage(err instanceof Error ? err.message : "Selection history could not be cleared.");
    } finally {
      setAuthBusy(false);
    }
  }

  async function handleDeleteAccount() {
    if (!window.confirm("Delete this local account and its learning history?")) return;
    setAuthBusy(true);
    try {
      await deleteMe();
      setAuthMessage("Account deleted.");
      setOutbox([]);
      await refresh(request, { selectTopRoom: true });
    } catch (err) {
      setAuthMessage(err instanceof Error ? err.message : "Account could not be deleted.");
    } finally {
      setAuthBusy(false);
    }
  }

  async function chooseRoom(roomId: string, source: "recommendation" | "room_detail") {
    setSelectedRoomId(roomId);
    setSelectionMessage(null);
    if (!isRealApi || !data?.authenticated) return;
    const recommendationRequestId = source === "recommendation" ? data.recommendations.request_id : null;
    try {
      await recordRoomSelection(roomId, recommendationRequestId, source);
      setSelectionMessage("Choice saved for preference learning.");
      await refresh(request);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Room choice could not be saved.";
      const roomName = data.rooms.find((room) => room.room_id === roomId)?.name ?? roomId;
      setOutbox((items) => [
        { id: `${Date.now()}-${roomId}`, roomId, roomName, source, recommendationRequestId, message },
        ...items,
      ].slice(0, 4));
      setSelectionMessage(`${message} Saved to retry queue.`);
    }
  }

  async function retrySelection(item: FailedSelection) {
    try {
      await recordRoomSelection(item.roomId, item.recommendationRequestId, item.source);
      setOutbox((items) => items.filter((entry) => entry.id !== item.id));
      setSelectionMessage(`Retried and saved ${item.roomName}.`);
      await refresh(request);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Retry failed.";
      setOutbox((items) => items.map((entry) => entry.id === item.id ? { ...entry, message } : entry));
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
          preferences={data?.preferences ?? null}
          history={data?.selectionHistory ?? null}
          outbox={outbox}
          onAuth={handleAuth}
          onLogout={handleLogout}
          onLearningToggle={handleLearningToggle}
          onResetLearned={handleResetLearned}
          onDeleteSelections={handleDeleteSelections}
          onDeleteAccount={handleDeleteAccount}
          onRetrySelection={retrySelection}
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
                history={data.histories[selectedRoom.room_id]?.points ?? []}
                thermalPreview={isRealApi ? liveSnapshot?.thermal_preview : data.thermalPreviews[selectedRoom.room_id]}
                sensorRoom={isRealApi ? liveSnapshot?.room ?? null : selectedRoom}
                soundPreview={isRealApi ? soundPreview : null}
                sensorError={isRealApi ? liveSensorError : null}
                liveMode={isRealApi}
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
  preferences,
  history,
  outbox,
  onAuth,
  onLogout,
  onLearningToggle,
  onResetLearned,
  onDeleteSelections,
  onDeleteAccount,
  onRetrySelection,
}: {
  user: DashboardData["user"];
  busy: boolean;
  message: string | null;
  preferences: DashboardData["preferences"];
  history: DashboardData["selectionHistory"];
  outbox: FailedSelection[];
  onAuth: (mode: "login" | "register", username: string, password: string) => Promise<void>;
  onLogout: () => Promise<void>;
  onLearningToggle: (enabled: boolean) => Promise<void>;
  onResetLearned: () => Promise<void>;
  onDeleteSelections: () => Promise<void>;
  onDeleteAccount: () => Promise<void>;
  onRetrySelection: (item: FailedSelection) => Promise<void>;
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
          <div className="session-toolbar">
            <span className="save-state">Session active</span>
            <button type="button" disabled={busy} onClick={() => void onLogout()}>
              Sign out
            </button>
          </div>
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={preferences?.learning_enabled ?? true}
              disabled={busy}
              onChange={(event) => void onLearningToggle(event.currentTarget.checked)}
            />
            Preference learning
          </label>
          {preferences ? <PreferenceEvidence preferences={preferences} /> : null}
          <div className="button-row">
            <button type="button" disabled={busy} onClick={() => void onResetLearned()}>
              Reset learned
            </button>
            <button type="button" disabled={busy} onClick={() => void onDeleteSelections()}>
              Clear choices
            </button>
            <button type="button" disabled={busy} onClick={() => void onDeleteAccount()}>
              Delete account
            </button>
          </div>
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
      {user && history?.selections.length ? <SelectionHistory selections={history.selections} /> : null}
      {outbox.length ? <SelectionOutbox items={outbox} busy={busy} onRetry={onRetrySelection} /> : null}
      {message ? <p className="inline-note">{message}</p> : null}
    </section>
  );
}

function PreferenceEvidence({ preferences }: { preferences: NonNullable<DashboardData["preferences"]> }) {
  const counts = preferences.evidence_counts;
  const total = counts.quiet_priority + counts.low_occupancy_priority + counts.brightness_priority + counts.comfort_priority;
  return (
    <div className="learning-strip">
      <span>Evidence {total}</span>
      <span>Quiet {formatMaybe(preferences.learned.quiet_priority)}</span>
      <span>Crowd {formatMaybe(preferences.learned.low_occupancy_priority)}</span>
      <span>Light {formatMaybe(preferences.learned.brightness_priority)}</span>
      <span>Comfort {formatMaybe(preferences.learned.comfort_priority)}</span>
    </div>
  );
}

function SelectionHistory({ selections }: { selections: NonNullable<DashboardData["selectionHistory"]>["selections"] }) {
  return (
    <div className="history-strip" aria-label="Recent room selections">
      <strong>Recent choices</strong>
      {selections.slice(0, 4).map((selection) => (
        <span key={selection.selection_id}>
          {selection.room_name}
          <small>{selection.selected_rank ? `#${selection.selected_rank}` : selection.source}</small>
        </span>
      ))}
    </div>
  );
}

function SelectionOutbox({ items, busy, onRetry }: { items: FailedSelection[]; busy: boolean; onRetry: (item: FailedSelection) => Promise<void> }) {
  return (
    <div className="outbox" aria-label="Retry queue">
      <strong>Retry queue</strong>
      {items.map((item) => (
        <span key={item.id}>
          {item.roomName}
          <small>{item.message}</small>
          <button type="button" disabled={busy} onClick={() => void onRetry(item)}>
            Retry
          </button>
        </span>
      ))}
    </div>
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
  history,
  thermalPreview,
  sensorRoom,
  soundPreview,
  sensorError,
  liveMode,
  selectionMessage,
  onChoose,
}: {
  room: RoomStatus;
  recommendation?: RecommendationItem;
  history: HistoryPoint[];
  thermalPreview?: ThermalPreviewResponse;
  sensorRoom: RoomStatus | null;
  soundPreview: SoundPreviewResponse | null;
  sensorError: string | null;
  liveMode: boolean;
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
      <SensorTelemetry
        room={sensorRoom}
        soundPreview={soundPreview}
        error={sensorError}
        liveMode={liveMode}
      />
      <div className="split">
        <TrendChart points={history} />
        <ThermalPreview preview={thermalPreview} />
      </div>
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

function SensorTelemetry({
  room,
  soundPreview,
  error,
  liveMode,
}: {
  room: RoomStatus | null;
  soundPreview: SoundPreviewResponse | null;
  error: string | null;
  liveMode: boolean;
}) {
  const features = room?.features;
  const currentSound = liveMode
    ? soundPreview?.available
      ? soundPreview.rms
      : null
    : features?.sound_rms_mean;
  const light = features?.light_lux != null
    ? `${features.light_lux.toFixed(1)} lx`
    : features?.light_relative_mean != null
      ? `${(features.light_relative_mean * 100).toFixed(1)}% relative`
      : "--";

  return (
    <section className="sensor-telemetry" aria-label="Live sensor readings">
      <div className="panel-heading">
        <div>
          <h3>Sensor readings</h3>
          <span className="muted">{liveMode ? "Current Raspberry Pi data" : "Mock aggregate data"}</span>
        </div>
        <span className={`sensor-link-state ${room ? "ok" : "offline"}`}>{room ? "Current" : "Unavailable"}</span>
      </div>
      {error ? <Notice tone="danger" text={`${error} Old sensor values are hidden.`} /> : null}
      <div className="sensor-metric-grid">
        <Metric label="Temperature" value={formatReading(features?.temperature_c, "°C", 1)} />
        <Metric label="Humidity" value={formatReading(features?.humidity_pct, "%", 1)} />
        <Metric label={features?.light_lux != null ? "Light" : "Relative light"} value={light} />
        <Metric label="Sound RMS (current)" value={formatPercent(currentSound, 4)} />
      </div>
      {room ? (
        <div className="sensor-health-row" aria-label="Sensor health">
          {Object.entries(room.sensor_health).map(([sensor, health]) => (
            <span className={`sensor-chip ${health}`} key={sensor}>
              {sensor}
              <small>{health}</small>
            </span>
          ))}
        </div>
      ) : null}
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
      <ModuleImplementationConsole data={data} rooms={rooms} staleRooms={staleRooms} offlineSensors={offlineSensors} degradedSensors={degradedSensors} averageConfidence={averageConfidence} />
    </section>
  );
}

function ModuleImplementationConsole({
  data,
  rooms,
  staleRooms,
  offlineSensors,
  degradedSensors,
  averageConfidence,
}: {
  data: DashboardData;
  rooms: RoomStatus[];
  staleRooms: RoomStatus[];
  offlineSensors: string[];
  degradedSensors: string[];
  averageConfidence: number;
}) {
  const recommendations = data.recommendations.recommendations;
  const selectionCount = data.selectionHistory?.selections.length ?? 0;
  const forecastCount = rooms.reduce((count, room) => count + room.forecasts.length, 0);
  const thermalAvailable = Object.values(data.thermalPreviews).filter((preview) => preview.available).length;
  const soundAvailable = rooms.filter((room) => room.features.sound_rms_mean != null).length;
  const explanationSources = Array.from(new Set(recommendations.map((item) => item.explanation_source))).join(", ") || "none";

  return (
    <section className="admin-internal" aria-label="Module implementation console">
      <div className="admin-section-title">
        <div>
          <p className="eyebrow">Internal implementation</p>
          <h2>Full project control view</h2>
          <p className="muted">Hardware signals, backend contracts, recommendation logic, and frontend guardrails are shown here for the final showcase.</p>
        </div>
        <span className="module-badge">Admin overview</span>
      </div>

      <div className="module-strip">
        <ModuleCard module="Module 1" title="Hardware sensing" value={`${thermalAvailable}/${rooms.length}`} detail="Thermal previews available" tone={thermalAvailable ? "ok" : "warning"} />
        <ModuleCard module="Module 2" title="Backend services" value={data.backendStatus.toUpperCase()} detail={`${rooms.length} rooms, ${forecastCount} forecasts`} tone={data.backendStatus === "ok" ? "ok" : "warning"} />
        <ModuleCard module="Module 3" title="ML recommendation" value={`${averageConfidence}%`} detail={`${recommendations.length} ranked rooms`} tone={averageConfidence >= 70 ? "ok" : "warning"} />
        <ModuleCard module="Module 4" title="Frontend console" value="Ready" detail="Student and admin views" tone="ok" />
      </div>

      <div className="implementation-grid">
        <section className="admin-panel implementation-panel">
          <div className="panel-heading">
            <h3>Hardware data pipeline</h3>
            <span className="module-badge">Module 1</span>
          </div>
          <PipelineStep index="01" title="Thermal sensor" detail={`${thermalAvailable} low-resolution thermal previews, ${rooms.reduce((sum, room) => sum + (room.features.thermal_hot_region_count ?? 0), 0)} hot regions currently detected.`} status={thermalAvailable ? "Live" : "Waiting"} />
          <PipelineStep index="02" title="Radar occupancy" detail={`${rooms.reduce((sum, room) => sum + (room.features.radar_active_target_count ?? 0), 0)} active targets aggregated without identity data.`} status={offlineSensors.some((item) => item.includes("radar")) ? "Check" : "Live"} />
          <PipelineStep index="03" title="Sound preview" detail={`${soundAvailable} RMS summaries available; raw voice storage remains blocked.`} status={soundAvailable ? "Privacy safe" : "No sample"} />
          <PipelineStep index="04" title="Environment signals" detail="Light, temperature, and humidity are consumed as numeric features for comfort scoring." status={degradedSensors.length ? "Degraded" : "Live"} />
        </section>

        <section className="admin-panel implementation-panel">
          <div className="panel-heading">
            <h3>Backend API surface</h3>
            <span className="module-badge">Module 2</span>
          </div>
          <div className="endpoint-list">
            <EndpointCard method="GET" path="/api/v1/rooms/status" detail={`${rooms.length} aggregate room states`} />
            <EndpointCard method="GET" path="/api/v1/rooms/{room_id}/live" detail="Room, thermal preview, and sound preview in one snapshot" />
            <EndpointCard method="POST" path="/api/v1/me/recommendations" detail="Authenticated recommendation request with learned preferences" />
            <EndpointCard method="GET" path="/api/v1/me/room-selections" detail={`${selectionCount} recent local choices loaded when signed in`} />
            <EndpointCard method="POST" path="/api/v1/me/preferences/reset-learned" detail="Reset learned weights without deleting manual preferences" />
          </div>
        </section>

        <section className="admin-panel implementation-panel">
          <div className="panel-heading">
            <h3>ML and ranking logic</h3>
            <span className="module-badge">Module 3</span>
          </div>
          <div className="model-stack">
            <ModelStage label="Feature vector" value="Thermal + radar + sound + environment" detail="Only aggregate, privacy-safe signals enter the recommender." />
            <ModelStage label="Forecast" value={`${forecastCount} horizons`} detail="15-minute and 30-minute occupancy forecasts support forward-looking choices." />
            <ModelStage label="Ranking" value={recommendations[0] ? `${recommendations[0].room_id} #1` : "No rank"} detail="Score combines study mode, occupancy, confidence, freshness, and fallback penalties." />
            <ModelStage label="Explanation" value={explanationSources} detail="Template explanations remain available when LLM generation is unavailable." />
          </div>
        </section>

        <section className="admin-panel implementation-panel">
          <div className="panel-heading">
            <h3>Showcase readiness</h3>
            <span className="module-badge">Module 4</span>
          </div>
          <div className="quality-list">
            <QualityItem label="Student experience" value="Complete: ranking, detail, privacy, learning controls" tone="ok" />
            <QualityItem label="Admin experience" value="Complete: health, modules, APIs, ML visibility" tone="ok" />
            <QualityItem label="Real hardware data" value={isRealApi ? "Requires live backend and devices" : "Mocked in this frontend demo"} tone="warning" />
            <QualityItem label="Production admin auth" value="Demo login only; backend auth needed for deployment" tone="warning" />
            <QualityItem label="Model training UI" value="Shown as status/logic, not executable in browser" tone="warning" />
          </div>
        </section>
      </div>
    </section>
  );
}

function ModuleCard({ module, title, value, detail, tone }: { module: string; title: string; value: string; detail: string; tone: "ok" | "warning" | "danger" }) {
  return (
    <article className={`module-card ${tone}`}>
      <span className="module-badge">{module}</span>
      <h3>{title}</h3>
      <strong>{value}</strong>
      <p>{detail}</p>
    </article>
  );
}

function PipelineStep({ index, title, detail, status }: { index: string; title: string; detail: string; status: string }) {
  return (
    <div className="pipeline-step">
      <span>{index}</span>
      <div>
        <strong>{title}</strong>
        <p>{detail}</p>
      </div>
      <small>{status}</small>
    </div>
  );
}

function EndpointCard({ method, path, detail }: { method: string; path: string; detail: string }) {
  return (
    <div className="endpoint-card">
      <span>{method}</span>
      <code>{path}</code>
      <p>{detail}</p>
    </div>
  );
}

function ModelStage({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="model-stage">
      <span>{label}</span>
      <strong>{value}</strong>
      <p>{detail}</p>
    </div>
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

function formatReading(value: number | null | undefined, unit: string, decimals: number) {
  return value == null || !Number.isFinite(value) ? "--" : `${value.toFixed(decimals)}${unit}`;
}

function formatPercent(value: number | null | undefined, decimals: number) {
  return value == null || !Number.isFinite(value) ? "--" : `${(value * 100).toFixed(decimals)}%`;
}

function formatMaybe(value?: number | null) {
  if (value == null) return "Unavailable";
  return value <= 1 ? value.toFixed(2) : `${Math.round(value)}`;
}

function formatTime(value?: string) {
  if (!value) return "pending";
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(value));
}
