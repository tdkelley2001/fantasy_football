import type {ReactNode} from "react";
import { currentMatchupPeriod } from "./LeagueOverviewContext";
import { ManagerSelectionStatus, type useManagerPerspective } from "./ManagerPerspective";
import type { SnapshotSummary } from "./types/api";

const snapshotTime = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

export function HomeDashboard({snapshot, managerState, children, openTeam, openMatchups,
  openLeague, openPlayoffRace, openSimulation, openTransactions}: {
  snapshot: SnapshotSummary;
  managerState: ReturnType<typeof useManagerPerspective>;
  children: ReactNode;
  openTeam: () => void;
  openMatchups: () => void;
  openLeague: () => void;
  openPlayoffRace: () => void;
  openSimulation: () => void;
  openTransactions: () => void;
}) {
  const state = managerState;
  const period = currentMatchupPeriod(snapshot);
  const team = state.team;
  const matchups = period && team ? snapshot.matchups.filter(item =>
    item.matchup_period_id === period.matchup_period_id &&
    (item.home_team_id === team.team_id || item.away_team_id === team.team_id),
  ) : [];

  return <div className="surface workspace-page product-home">
    <section className="hero workspace-page-heading">
      <div><h1>Home</h1><h2>{snapshot.league_name ?? "Current league"} / {snapshot.season}</h2>
        <p>Snapshot · {snapshotTime.format(new Date(snapshot.retrieval_finished_at_utc))}</p>
      </div>
    </section>
    {team ? <div className="home-briefing">
      <section className="home-summary">
        <h2>{team.display_name}</h2>
        <p>{state.perspective?.display_name}</p>
        <dl>
          <div><dt>Record</dt><dd>{team.wins}–{team.losses}–{team.ties}</dd></div>
          <div><dt>Standing</dt><dd>{team.standing ?? "Unavailable"}</dd></div>
          <div><dt>Points for</dt><dd>{team.points_for.toFixed(1)}</dd></div>
        </dl>
        <button className="workspace-action" type="button" onClick={openTeam}>View team roster</button>
      </section>
      <section className="home-summary">
        <h2>Current matchup</h2>
        {period && matchups.length ? <>
          <p>Snapshot pairings / Scoring {period.scoring_weeks.length === 1 ? "week" : "weeks"} {period.scoring_weeks.join(", ")}</p>
          <ul>{matchups.map(item => {
            if (item.entry_status === "bye") return <li key={item.matchup_id}>Bye</li>;
            const home = item.home_team_id === team.team_id;
            const opponentId = home ? item.away_team_id : item.home_team_id;
            const opponent = opponentId === null ? undefined : state.teams.get(opponentId);
            return <li key={item.matchup_id}>
              {opponent ? `${home ? "Home vs." : "Away at"} ${opponent.display_name}` : "Opponent unavailable"}
              {item.entry_status==="scheduled" && <small className="bracket-context"> / Scheduled pairing</small>}
            </li>;
          })}</ul>
        </> : <p>No confirmed pairing for this team in the current scoring period.</p>}
        <button className="workspace-action" type="button" onClick={openMatchups}>View league matchups</button>
      </section>
    </div> : <ManagerSelectionStatus state={state}/>}
    {children}
    <nav className="home-shortcuts" aria-label="League and analysis shortcuts">
      <button className="workspace-action" type="button" onClick={openLeague}>View projected season details</button>
      <button className="workspace-action" type="button" onClick={openPlayoffRace}>Open Playoff Race</button>
      <button className="workspace-action" type="button" onClick={openSimulation}>Open Simulation Center</button>
      <button className="workspace-action" type="button" onClick={openTransactions}>Explore transactions</button>
    </nav>
  </div>;
}
