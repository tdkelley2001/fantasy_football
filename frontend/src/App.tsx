import { useEffect, useRef, useState } from "react";
import { Activity, Database, FlaskConical, LayoutGrid, Menu, Moon, RefreshCw, Settings, ShieldCheck, Sun, Trophy, Users, X } from "lucide-react";
import { api, ApiError } from "./lib/api";
import type { BackgroundRunRecord, HealthResponse, SnapshotSummary } from "./types/api";
import { LeagueOverview } from "./LeagueOverview";

type Destination = "league" | "opportunities" | "trades" | "simulation";
type Theme = "dark" | "light";
const nav: readonly [Destination, string, typeof Users][] = [
  ["league", "League Overview", Users], ["opportunities", "Opportunity Explorer", LayoutGrid],
  ["trades", "Trade Lab", FlaskConical], ["simulation", "Simulation Center", Activity],
];

function initialTheme(): Theme {
  const stored = localStorage.getItem("war-room-theme");
  if (stored === "dark" || stored === "light") return stored;
  return matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [destination, setDestination] = useState<Destination>("league");
  const [health, setHealth] = useState<HealthResponse>();
  const [snapshots, setSnapshots] = useState<readonly SnapshotSummary[]>([]);
  const [selected, setSelected] = useState<SnapshotSummary>();
  const [runs, setRuns] = useState<readonly BackgroundRunRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError>();
  const [contextOpen, setContextOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const requestVersion=useRef(0); const activeController=useRef<AbortController|undefined>(undefined);
  const contextTrigger=useRef<HTMLButtonElement>(null); const contextClose=useRef<HTMLButtonElement>(null);

  const load = async (signal?: AbortSignal) => {
    const version=++requestVersion.current;
    setLoading(true); setError(undefined);
    try {
      const [nextHealth, nextSnapshots, nextRuns] = await Promise.all([
        api.health(signal), api.snapshots(signal), api.runs(signal),
      ]);
      if(signal?.aborted||version!==requestVersion.current)return;
      setHealth(nextHealth); setSnapshots(nextSnapshots); setRuns(nextRuns);
      if (nextSnapshots.length) {
        const saved = localStorage.getItem("war-room-snapshot");
        const id = nextSnapshots.some((item) => item.snapshot_id === saved) ? saved! : nextSnapshots[0].snapshot_id;
        const detail=await api.snapshot(id, signal);
        if(signal?.aborted||version!==requestVersion.current)return;
        setSelected(detail);
        localStorage.setItem("war-room-snapshot", id);
      } else setSelected(undefined);
    } catch (cause) {
      if (!(cause instanceof DOMException && cause.name === "AbortError") && version===requestVersion.current) { setHealth(undefined); setError(cause instanceof ApiError ? cause : new ApiError("Unexpected application error.", -1)); }
    } finally { if (!signal?.aborted&&version===requestVersion.current) setLoading(false); }
  };

  useEffect(() => { const controller = new AbortController(); activeController.current=controller; void load(controller.signal); return () => {requestVersion.current++;controller.abort();}; }, []);
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem("war-room-theme", theme); }, [theme]);
  useEffect(()=>{if(!contextOpen)return;contextClose.current?.focus();const close=(event:KeyboardEvent)=>{if(event.key==="Escape"){setContextOpen(false);contextTrigger.current?.focus();}};document.addEventListener("keydown",close);return()=>document.removeEventListener("keydown",close);},[contextOpen]);

  const chooseSnapshot = async (id: string) => {
    activeController.current?.abort(); const controller=new AbortController(); activeController.current=controller; const version=++requestVersion.current;
    setLoading(true); setError(undefined);
    try { const detail=await api.snapshot(id,controller.signal); if(controller.signal.aborted||version!==requestVersion.current)return; setSelected(detail); localStorage.setItem("war-room-snapshot", id); }
    catch (cause) { if (!(cause instanceof DOMException&&cause.name==="AbortError")&&version===requestVersion.current) setError(cause instanceof ApiError ? cause : new ApiError("Snapshot could not be loaded.", -1)); }
    finally { if(!controller.signal.aborted&&version===requestVersion.current)setLoading(false); }
  };
  const activeRuns = runs.filter((run) => ["queued", "running", "cancel_requested"].includes(run.status));

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to strategy surface</a>
    <aside className={`rail ${menuOpen ? "rail-open" : ""}`} aria-label="Primary navigation">
      <div className="brand"><div className="brand-mark"><Trophy size={20}/></div><div><strong>War Room</strong><span>Fantasy intelligence</span></div></div>
      <nav>{nav.map(([id, label, Icon]) => <button key={id} className={destination === id ? "active" : ""} aria-current={destination === id ? "page" : undefined} onClick={() => { setDestination(id); setMenuOpen(false); }}><Icon size={18}/><span>{label}</span></button>)}</nav>
      <div className="rail-footer"><span className={`status-dot ${health ? "online" : ""}`}/><div><strong>{health ? "Engine connected" : "Engine offline"}</strong><span>Local analytical service</span></div></div>
    </aside>
    <header className="command-bar">
      <button className="icon-button mobile-only" aria-label="Open navigation" onClick={() => setMenuOpen(true)}><Menu/></button>
      <label className="snapshot-control"><span>Active snapshot</span><select aria-label="Active snapshot" aria-busy={loading} value={selected?.snapshot_id ?? ""} disabled={!snapshots.length} onChange={(e) => void chooseSnapshot(e.target.value)}>{!snapshots.length && <option value="">No snapshots</option>}{snapshots.map((snapshot) => <option key={snapshot.snapshot_id} value={snapshot.snapshot_id}>{snapshot.league_name ?? `League ${snapshot.league_id}`} · {snapshot.season}</option>)}</select></label>
      <div className="command-actions">
        <div className="run-indicator" aria-live="polite"><Activity size={16}/><span>{activeRuns.length ? `${activeRuns.length} active` : "No active runs"}</span></div>
        <button className="icon-button" aria-label={`Use ${theme === "dark" ? "light" : "dark"} theme`} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? <Sun/> : <Moon/>}</button>
        <button ref={contextTrigger} className="icon-button" aria-label="Open league context" onClick={() => setContextOpen(!contextOpen)}><Settings/></button>
      </div>
    </header>
    {menuOpen && <button className="scrim" aria-label="Close navigation" onClick={() => setMenuOpen(false)}/>} 
    <main id="main-content" tabIndex={-1}>
      {loading && !selected ? <LoadingState/> : error ? <FailureState error={error} retry={() => {activeController.current?.abort();const controller=new AbortController();activeController.current=controller;void load(controller.signal);}}/> : !selected ? <EmptyState/> : destination === "league" ? <LeagueOverview snapshot={selected}/> : <FutureWorkspace destination={destination} activeRuns={activeRuns}/>}
    </main>
    <aside className={`context-panel ${contextOpen ? "context-open" : ""}`} aria-label="League context" aria-hidden={!contextOpen}>
      <div className="context-head"><div><span className="eyebrow">Decision context</span><h2>Source & build</h2></div><button ref={contextClose} disabled={!contextOpen} className="icon-button" aria-label="Close league context" onClick={() => {setContextOpen(false);contextTrigger.current?.focus();}}><X/></button></div>
      {selected ? <><Info label="Snapshot" value={selected.snapshot_id}/><Info label="Published" value={formatDate(selected.published_at_utc)}/><Info label="Canonical model" value={`Schema v${selected.canonical_schema_version}`}/><Info label="Evidence sources" value={`${selected.source_count} linked`}/><Info label="Simulation horizon" value={`Weeks ${selected.first_simulation_week}–${selected.final_simulation_week}`}/></> : <p>No snapshot selected.</p>}
      {health && <div className="build-card"><ShieldCheck/><div><strong>API contract {health.api_schema_version}</strong><span>{health.package_version} · {health.build_revision ?? "revision unavailable"}</span></div></div>}
    </aside>
    <nav className="mobile-nav" aria-label="Mobile primary navigation">{nav.map(([id, label, Icon]) => <button key={id} className={destination === id ? "active" : ""} aria-label={label} onClick={() => setDestination(id)}><Icon/><span>{label.split(" ")[0]}</span></button>)}</nav>
  </div>;
}

function FutureWorkspace({ destination, activeRuns }: { destination: Destination; activeRuns: readonly BackgroundRunRecord[] }) {
  const labels = { opportunities: ["Opportunity Explorer", "Acquisition and streaming discovery arrives in M7.3."], trades: ["Trade Lab", "Manual and automated scenario interaction arrives in M7.4."], simulation: ["Simulation Center", "Run submission and progressive results arrive in M7.5."], league: ["League Overview", ""] } as const;
  const [title, copy] = labels[destination];
  return <div className="surface"><section className="hero"><div><span className="eyebrow">Application shell · future workspace</span><h1>{title}</h1><p>{copy}</p></div></section><article className="card placeholder"><div className="placeholder-orbit"><Activity/></div><h2>Foundation connected</h2><p>This destination is intentionally non-operational in M7.1. No analytical capability is implied by this shell.</p><div className="placeholder-status"><span>{activeRuns.length}</span> active backend runs visible</div></article></div>;
}

function FailureState({ error, retry }: { error: ApiError; retry: () => void }) { const disconnected = error.status === 0; return <div className="state-card" role="alert"><div className="state-icon">{disconnected ? <Database/> : <ShieldCheck/>}</div><span className="eyebrow">{disconnected ? "Local service disconnected" : "Request failed"}</span><h1>{disconnected ? "Reconnect the decision engine" : "The War Room could not load"}</h1><p>{error.message}</p><button className="primary-button" onClick={retry}><RefreshCw/>Try again</button></div>; }
function EmptyState() { return <div className="state-card"><div className="state-icon"><Database/></div><span className="eyebrow">Snapshot library</span><h1>No canonical snapshots yet</h1><p>Retrieve and persist a league snapshot through the accepted backend workflow, then return here.</p></div>; }
function LoadingState() { return <div className="surface" aria-busy="true" aria-label="Loading War Room"><div className="skeleton hero-skeleton"/><div className="league-grid"><div className="skeleton card"/><div className="skeleton card"/><div className="skeleton card"/></div></div>; }
function Info({ label,value }: { label:string; value:string }) { return <div className="info-row"><span>{label}</span><strong>{value}</strong></div>; }
function formatDate(value:string) { return new Intl.DateTimeFormat(undefined,{dateStyle:"medium",timeStyle:"short"}).format(new Date(value)); }
