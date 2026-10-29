import { useEffect, useMemo, useState } from "react";
import { Activity, ArrowUpRight, Database, FlaskConical, LayoutGrid, Menu, Moon, RefreshCw, Settings, ShieldCheck, Sun, Trophy, Users, X } from "lucide-react";
import { api, ApiError } from "./lib/api";
import type { BackgroundRunRecord, HealthResponse, SnapshotSummary } from "./types/api";

type Destination = "league" | "opportunities" | "trades" | "simulation";
type Theme = "dark" | "light";
const nav: readonly [Destination, string, typeof Users][] = [
  ["league", "Living League", Users], ["opportunities", "Opportunity Explorer", LayoutGrid],
  ["trades", "Trade Lab", FlaskConical], ["simulation", "Simulation Control", Activity],
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

  const load = async () => {
    setLoading(true); setError(undefined);
    const controller = new AbortController();
    try {
      const [nextHealth, nextSnapshots, nextRuns] = await Promise.all([
        api.health(controller.signal), api.snapshots(controller.signal), api.runs(controller.signal),
      ]);
      setHealth(nextHealth); setSnapshots(nextSnapshots); setRuns(nextRuns);
      if (nextSnapshots.length) {
        const saved = localStorage.getItem("war-room-snapshot");
        const id = nextSnapshots.some((item) => item.snapshot_id === saved) ? saved! : nextSnapshots[0].snapshot_id;
        setSelected(await api.snapshot(id, controller.signal));
        localStorage.setItem("war-room-snapshot", id);
      } else setSelected(undefined);
    } catch (cause) {
      if (!(cause instanceof DOMException && cause.name === "AbortError")) setError(cause instanceof ApiError ? cause : new ApiError("Unexpected application error.", -1));
    } finally { setLoading(false); }
    return () => controller.abort();
  };

  useEffect(() => { void load(); }, []);
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem("war-room-theme", theme); }, [theme]);

  const chooseSnapshot = async (id: string) => {
    setLoading(true); setError(undefined);
    try { setSelected(await api.snapshot(id)); localStorage.setItem("war-room-snapshot", id); }
    catch (cause) { setError(cause instanceof ApiError ? cause : new ApiError("Snapshot could not be loaded.", -1)); }
    finally { setLoading(false); }
  };
  const activeRuns = runs.filter((run) => ["queued", "running", "cancel_requested"].includes(run.status));
  const selectedLabel = snapshots.find((item) => item.snapshot_id === selected?.snapshot_id);

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to strategy surface</a>
    <aside className={`rail ${menuOpen ? "rail-open" : ""}`} aria-label="Primary navigation">
      <div className="brand"><div className="brand-mark"><Trophy size={20}/></div><div><strong>War Room</strong><span>Fantasy intelligence</span></div></div>
      <nav>{nav.map(([id, label, Icon]) => <button key={id} className={destination === id ? "active" : ""} aria-current={destination === id ? "page" : undefined} onClick={() => { setDestination(id); setMenuOpen(false); }}><Icon size={18}/><span>{label}</span></button>)}</nav>
      <div className="rail-footer"><span className={`status-dot ${health ? "online" : ""}`}/><div><strong>{health ? "Engine connected" : "Engine offline"}</strong><span>Local analytical service</span></div></div>
    </aside>
    <header className="command-bar">
      <button className="icon-button mobile-only" aria-label="Open navigation" onClick={() => setMenuOpen(true)}><Menu/></button>
      <label className="snapshot-control"><span>Active snapshot</span><select aria-label="Active snapshot" value={selected?.snapshot_id ?? ""} disabled={!snapshots.length || loading} onChange={(e) => void chooseSnapshot(e.target.value)}>{!snapshots.length && <option value="">No snapshots</option>}{snapshots.map((snapshot) => <option key={snapshot.snapshot_id} value={snapshot.snapshot_id}>{snapshot.league_name ?? `League ${snapshot.league_id}`} · {snapshot.season}</option>)}</select></label>
      <div className="command-actions">
        <div className="run-indicator" aria-live="polite"><Activity size={16}/><span>{activeRuns.length ? `${activeRuns.length} active` : "No active runs"}</span></div>
        <button className="icon-button" aria-label={`Use ${theme === "dark" ? "light" : "dark"} theme`} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? <Sun/> : <Moon/>}</button>
        <button className="icon-button" aria-label="Open league context" onClick={() => setContextOpen(!contextOpen)}><Settings/></button>
      </div>
    </header>
    {menuOpen && <button className="scrim" aria-label="Close navigation" onClick={() => setMenuOpen(false)}/>} 
    <main id="main-content" tabIndex={-1}>
      {loading && !selected ? <LoadingState/> : error ? <FailureState error={error} retry={() => void load()}/> : !selected ? <EmptyState/> : destination === "league" ? <LivingLeague snapshot={selected}/> : <FutureWorkspace destination={destination} activeRuns={activeRuns}/>} 
    </main>
    <aside className={`context-panel ${contextOpen ? "context-open" : ""}`} aria-label="League context">
      <div className="context-head"><div><span className="eyebrow">Decision context</span><h2>Source & build</h2></div><button className="icon-button" aria-label="Close league context" onClick={() => setContextOpen(false)}><X/></button></div>
      {selected ? <><Info label="Snapshot" value={selected.snapshot_id}/><Info label="Published" value={formatDate(selected.published_at_utc)}/><Info label="Canonical model" value={`Schema v${selected.canonical_schema_version}`}/><Info label="Evidence sources" value={`${selected.source_count} linked`}/><Info label="Simulation horizon" value={`Weeks ${selected.first_simulation_week}–${selected.final_simulation_week}`}/></> : <p>No snapshot selected.</p>}
      {health && <div className="build-card"><ShieldCheck/><div><strong>API contract {health.api_schema_version}</strong><span>{health.package_version} · {health.build_revision ?? "revision unavailable"}</span></div></div>}
    </aside>
    <nav className="mobile-nav" aria-label="Mobile primary navigation">{nav.map(([id, label, Icon]) => <button key={id} className={destination === id ? "active" : ""} aria-label={label} onClick={() => setDestination(id)}><Icon/><span>{label.split(" ")[0]}</span></button>)}</nav>
  </div>;
}

function LivingLeague({ snapshot }: { snapshot: SnapshotSummary }) {
  const teams = [...snapshot.teams].sort((a,b) => (a.standing ?? 999) - (b.standing ?? 999) || a.team_id-b.team_id);
  const teamById = useMemo(() => new Map(teams.map((team) => [team.team_id, team])), [snapshot.snapshot_id]);
  const period = snapshot.matchup_periods.find((item) => item.scoring_weeks.includes(snapshot.first_simulation_week)) ?? snapshot.matchup_periods[0];
  const matchups = snapshot.matchups.filter((item) => item.matchup_period_id === period?.matchup_period_id);
  return <div className="surface">
    <section className="hero"><div><span className="eyebrow">Living League · source-backed</span><h1>{snapshot.league_name ?? `League ${snapshot.league_id}`}</h1><p>{snapshot.season} season · {teams.length} teams · decision horizon weeks {snapshot.first_simulation_week}–{snapshot.final_simulation_week}</p></div><div className="source-seal"><Database/><div><strong>Canonical snapshot</strong><span>{formatDate(snapshot.published_at_utc)}</span></div></div></section>
    <section className="league-grid">
      <article className="card standings"><CardHead kicker="Competitive order" title="League table" meta={`${teams.length} clubs`}/><div className="table-wrap"><table><thead><tr><th>Rank</th><th>Team</th><th>Record</th><th>Points</th></tr></thead><tbody>{teams.map((team) => <tr key={team.team_id}><td><span className="rank">{team.standing ?? "—"}</span></td><td><strong>{team.display_name}</strong><small>{team.playoff_seed ? `Seed ${team.playoff_seed}` : "Seed unresolved"}</small></td><td>{team.wins}-{team.losses}{team.ties ? `-${team.ties}` : ""}</td><td>{team.points_for.toFixed(1)}</td></tr>)}</tbody></table></div></article>
      <article className="card pitch-card"><CardHead kicker="Tactical field" title="League pressure map" meta="Standings only"/><div className="pitch" aria-label="Top league positions"><div className="midfield"/>{teams.slice(0,6).map((team, index) => <div key={team.team_id} className={`team-chip chip-${index}`}><span>{team.standing ?? index+1}</span><strong>{initials(team.display_name)}</strong><small>{team.wins}-{team.losses}</small></div>)}</div><p className="caption">A spatial view of current standings—not a probability forecast.</p></article>
      <article className="card matchups"><CardHead kicker="Schedule intelligence" title={period ? `Matchup period ${period.matchup_period_id}` : "Upcoming matchups"} meta={period ? `Weeks ${period.scoring_weeks.join(", ")}` : "Unresolved"}/><div className="matchup-list">{matchups.length ? matchups.map((game) => <div className="matchup" key={game.matchup_id}><TeamLine team={game.away_team_id ? teamById.get(game.away_team_id) : undefined}/><span className="versus">VS</span><TeamLine team={game.home_team_id ? teamById.get(game.home_team_id) : undefined}/><small>{game.bracket_type ?? period?.phase ?? "scheduled"}</small></div>) : <p className="quiet">No matchup records are available for this decision period.</p>}</div></article>
      <article className="card intel"><CardHead kicker="Roster intelligence" title="Snapshot coverage" meta="Observed data"/><div className="metric-grid"><Metric value={snapshot.players.length} label="Players"/><Metric value={snapshot.roster_assignments.length} label="Assignments"/><Metric value={snapshot.capabilities.filter(c => c.status.toLowerCase().includes("verified") || c.status.toLowerCase().includes("supported")).length} label="Supported rules"/><Metric value={snapshot.source_count} label="Evidence sources"/></div><div className="insight"><ArrowUpRight/><p><strong>Strategy surfaces are connected.</strong><span>Opportunity, trade, and simulation workspaces arrive in later M7 packages.</span></p></div></article>
    </section>
  </div>;
}

function FutureWorkspace({ destination, activeRuns }: { destination: Destination; activeRuns: readonly BackgroundRunRecord[] }) {
  const labels = { opportunities: ["Opportunity Explorer", "Acquisition and streaming discovery arrives in M7.2."], trades: ["Trade Lab", "Manual and automated scenario interaction arrives in M7.3."], simulation: ["Simulation Control", "Run submission and progressive results arrive in M7.4."], league: ["Living League", ""] } as const;
  const [title, copy] = labels[destination];
  return <div className="surface"><section className="hero"><div><span className="eyebrow">Application shell · future workspace</span><h1>{title}</h1><p>{copy}</p></div></section><article className="card placeholder"><div className="placeholder-orbit"><Activity/></div><h2>Foundation connected</h2><p>This destination is intentionally non-operational in M7.1. No analytical capability is implied by this shell.</p><div className="placeholder-status"><span>{activeRuns.length}</span> active backend runs visible</div></article></div>;
}

function FailureState({ error, retry }: { error: ApiError; retry: () => void }) { const disconnected = error.status === 0; return <div className="state-card" role="alert"><div className="state-icon">{disconnected ? <Database/> : <ShieldCheck/>}</div><span className="eyebrow">{disconnected ? "Local service disconnected" : "Request failed"}</span><h1>{disconnected ? "Reconnect the decision engine" : "The War Room could not load"}</h1><p>{error.message}</p><button className="primary-button" onClick={retry}><RefreshCw/>Try again</button></div>; }
function EmptyState() { return <div className="state-card"><div className="state-icon"><Database/></div><span className="eyebrow">Snapshot library</span><h1>No canonical snapshots yet</h1><p>Retrieve and persist a league snapshot through the accepted backend workflow, then return here.</p></div>; }
function LoadingState() { return <div className="surface" aria-busy="true" aria-label="Loading War Room"><div className="skeleton hero-skeleton"/><div className="league-grid"><div className="skeleton card"/><div className="skeleton card"/><div className="skeleton card"/></div></div>; }
function CardHead({ kicker,title,meta }: { kicker:string; title:string; meta:string }) { return <header className="card-head"><div><span className="eyebrow">{kicker}</span><h2>{title}</h2></div><span>{meta}</span></header>; }
function TeamLine({ team }: { team: SnapshotSummary["teams"][number] | undefined }) { return <div className="team-line"><span>{team ? initials(team.display_name) : "—"}</span><strong>{team?.display_name ?? "TBD"}</strong></div>; }
function Metric({ value,label }: { value:number; label:string }) { return <div className="metric"><strong>{value}</strong><span>{label}</span></div>; }
function Info({ label,value }: { label:string; value:string }) { return <div className="info-row"><span>{label}</span><strong>{value}</strong></div>; }
function initials(name:string) { return name.split(/\s+/).map(p=>p[0]).join("").slice(0,3).toUpperCase(); }
function formatDate(value:string) { return new Intl.DateTimeFormat(undefined,{dateStyle:"medium",timeStyle:"short"}).format(new Date(value)); }
