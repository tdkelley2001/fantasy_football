import type {ReactNode} from "react";
import { currentMatchupPeriod } from "./LeagueOverviewContext";
import type { useManagerPerspective } from "./ManagerPerspective";
import type { ProjectedBaselineResult, SnapshotSummary } from "./types/api";

const snapshotTime = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

export function HomeDashboard({snapshot, projected, profileUnavailable, managerState, children, openTeam, openMatchups}: {
  snapshot: SnapshotSummary;
  projected?: ProjectedBaselineResult;
  profileUnavailable: boolean;
  managerState: ReturnType<typeof useManagerPerspective>;
  children: ReactNode;
  openTeam: () => void;
  openMatchups: () => void;
}) {
  const state = managerState;
  const period = currentMatchupPeriod(snapshot);
  const team = state.team;
  const matchups = period && team ? snapshot.matchups.filter(item =>
    item.matchup_period_id === period.matchup_period_id &&
    (item.home_team_id === team.team_id || item.away_team_id === team.team_id),
  ) : [];

  const observedLeaders = snapshot.teams.filter(item=>item.standing===1);
  const projectedLeaders = projected?.teams.filter(item=>item.final_regular_rank===1);
  const scoringWeek = snapshot.live_scoring?.current_scoring_period;
  const freshness = new Date(snapshot.retrieval_finished_at_utc);

  return <div className="surface workspace-page product-home">
    <section className="home-season-lead" aria-label="League season">
      <div className="home-edition">
        <p className="home-kicker">{snapshot.season} season{scoringWeek!=null && ` / Week ${scoringWeek}`}</p>
        <h1>{snapshot.league_name ?? "Current league"}</h1>
        {Number.isFinite(freshness.getTime()) && <p className="home-freshness">
          Snapshot <time dateTime={freshness.toISOString()}>{snapshotTime.format(freshness)}</time>
        </p>}
        {profileUnavailable && <p className="home-freshness" role="status">ESPN connection unavailable. This snapshot has not been verified against the configured league.</p>}
      </div>
      <dl className="home-season-story">
        <div>
          <dt>Observed</dt>
          <dd>{observedLeaders.length
            ? observedLeaders.map(item=>item.display_name).join(", ")
            : "League leader unavailable"}</dd>
          {observedLeaders.length>0 && <dd className="home-story-caption">
            {observedLeaders.length===1 ? "Leads the standings" : "Share first in the standings"}
          </dd>}
        </div>
        <div>
          <dt>Projected season</dt>
          <dd>{projectedLeaders?.length
            ? projectedLeaders.map(item=>snapshot.teams.find(candidate=>candidate.team_id===item.team_id)?.display_name).filter(Boolean).join(", ") || "Projected leader unavailable"
            : projected ? "Projected leader unavailable" : "See season outlook below"}</dd>
          {Boolean(projectedLeaders?.length) && <dd className="home-story-caption">Projected regular-season first place</dd>}
        </div>
      </dl>
    </section>
    {children}
    {team && <details className="home-personal">
      <summary>Your team / {team.display_name}</summary>
      <div className="home-briefing">
      <section className="home-summary">
        <h2>{team.display_name}</h2>
        <p>{state.perspective?.display_name}</p>
        <dl>
          <div><dt>Record</dt><dd>{team.wins}–{team.losses}–{team.ties}</dd></div>
          <div><dt>Standing</dt><dd>{team.standing ?? "Unavailable"}</dd></div>
          <div><dt>Points for</dt><dd>{team.points_for.toFixed(1)}</dd></div>
        </dl>
        <button id="home-roster" className="workspace-action" type="button" onClick={openTeam}>View team roster</button>
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
        <button id="home-current-matchup" className="workspace-action" type="button" onClick={openMatchups}>View league matchups</button>
      </section>
      </div>
    </details>}
  </div>;
}
