import type {ProjectedSeasonState} from "./useProjectedSeason";
import { useEffect, useMemo, useRef, useState } from "react";
import { Activity, AlertTriangle, BarChart3, Database, ShieldCheck, Trophy } from "lucide-react";
import { JourneyTeamWeeks, SeasonJourney } from "./SeasonJourney";
import { commandTeamColor } from "./commandTeamIdentity";
import { ProjectedBracket } from "./ProjectedBracket";
import { ProjectedBaseline, ProjectionReadiness } from "./ProjectedBaseline";
import { api, ApiError, projectedBaselinePolicy } from "./lib/api";
import type { BackgroundBaselineResultSummary, BackgroundRunRecord, BaselineAnalysisRequest, ProjectedBaselineResult, ProbabilityValue, SnapshotSummary, TeamProbabilityResult, TeamSummary } from "./types/api";

import { CurrentMatchups, PreviousChampionship, RecentResults } from "./LeagueOverviewContext";

export type ForecastRequest = { canonical: string; request: BaselineAnalysisRequest };
export type ForecastMode = "projected" | "monte_carlo";

type OverviewProps = {
  layered?: boolean;
  snapshot: SnapshotSummary; projection?: ProjectedSeasonState; openSimulation?: () => void;
  openArchive?: (year: number) => void; openPlayoffRace?: () => void;
  openCompatibleSimulation?: () => void;
  runs?: readonly BackgroundRunRecord[];
  runListStatus?: "loading" | "loaded" | "unavailable";
  loadRuns?: typeof api.runs;
  forecastRequests?: ReadonlyMap<string,ForecastRequest>;
  modePreference?: { choice: ForecastMode | undefined; select: (mode: ForecastMode) => void };
};
export function LeagueOverview({snapshot, projection, openSimulation, openArchive, openPlayoffRace, openCompatibleSimulation, runs, runListStatus, loadRuns, modePreference, forecastRequests}: OverviewProps) {
  return <div className="overview analytics-overview"><header className="overview-masthead"><div><span className="overline">League overview</span><h1>{snapshot.league_name??`League ${snapshot.league_id}`}</h1><p>{snapshot.season} season · {snapshot.teams.length} teams · weeks {snapshot.first_simulation_week}–{snapshot.final_simulation_week}</p></div><div className="snapshot-stamp"><Database/><span><strong>Canonical snapshot</strong>{formatDate(snapshot.published_at_utc)}</span></div></header>
    <CommandCenter key={JSON.stringify([snapshot.snapshot_id,snapshot.canonical_sha256])}
      snapshot={snapshot} projection={projection} runs={runs} runListStatus={runListStatus}
      loadRuns={loadRuns} forecastRequests={forecastRequests} modePreference={modePreference} openCompatibleSimulation={openCompatibleSimulation}/>
    <div className="overview-source-grid"><div className="overview-source-stack"><ObservedSnapshot snapshot={snapshot}/><RecentResults key={snapshot.snapshot_id} snapshot={snapshot}/></div><div className="overview-source-stack"><CurrentMatchups snapshot={snapshot}/>{openArchive&&<PreviousChampionship leagueId={snapshot.league_id} season={snapshot.season} openArchive={openArchive}/>}</div></div>{projection&&<details className="run-disclosure" open={!runs?.some(run=>run.run_type==="baseline"&&run.status==="completed"&&run.snapshot_id===snapshot.snapshot_id)}><summary>Projected season details</summary><ProjectedBaseline snapshot={snapshot} projection={projection} openSimulation={openSimulation}/></details>}{openPlayoffRace && <section className="analytics-panel workspace-panel">
    <h2>Playoff outlook</h2>
    <p>See retained War Room probabilities, placement distributions and run details.</p>
    <button className="workspace-action" type="button" onClick={openPlayoffRace}>Open Playoff Race</button>
  </section>}</div>;
}

type PlayoffRaceProps = {
  snapshot: SnapshotSummary; runs: readonly BackgroundRunRecord[];
  runListStatus?: "loading" | "loaded" | "unavailable"; preferredRunId?: string | null;
  openSimulation?: () => void;
};
export function PlayoffRace({snapshot, runs, runListStatus="loaded", preferredRunId, openSimulation}: PlayoffRaceProps) {
  const {completed, selectedRun, setSelectedRun, loading, error, activeSummary, matching} =
    useBaselineForecast(snapshot, runs, runListStatus, preferredRunId);
  return <div className="overview analytics-overview playoff-race-page"><header className="overview-masthead">
    <div><h1>Playoff Race</h1><p>{snapshot.league_name ?? `League ${snapshot.league_id}`} / {snapshot.season}</p></div>
    <div className="snapshot-stamp"><Database/><span><strong>Canonical snapshot</strong>{formatDate(snapshot.published_at_utc)}</span></div>
  </header>
  {openSimulation && <div className="playoff-actions">
    <button className="workspace-action" type="button" onClick={openSimulation}>Open Simulation Center</button>
  </div>}
  {runListStatus!=="loaded"?<AnalyticsState icon={<Activity/>} title={runListStatus==="loading"?"Checking retained runs":"Retained baseline results unavailable"} body={runListStatus==="loading"?"Loading the run list.":"Use Retry run list to check for retained Monte Carlo analysis."}/>:<><RunContext completed={completed} selected={selectedRun} onChange={setSelectedRun}/>{loading?<AnalyticsState icon={<Activity/>} title="Loading retained analysis" body="Reading the selected completed run without starting new simulation work."/>:error?<AnalyticsState icon={<AlertTriangle/>} title="Result unavailable" body={error}/>:activeSummary?<AnalyticsDashboard snapshot={snapshot} summary={activeSummary}/>:<NoAnalysis runs={matching}/>}</>}</div>;
}

const noRuns: readonly BackgroundRunRecord[] = [];

function compatibleRequest(snapshot: SnapshotSummary, evidence: ForecastRequest | undefined) {
  if (!evidence || evidence.canonical!==snapshot.canonical_sha256) return false;
  const {snapshot: selector, simulation} = evidence.request;
  return selector.snapshot_id===snapshot.snapshot_id && selector.league_id===snapshot.league_id &&
    selector.season===snapshot.season && simulation.ir_policy===projectedBaselinePolicy.ir_policy &&
    simulation.waiver_boundary===projectedBaselinePolicy.waiver_boundary &&
    simulation.reject_incomplete_valuations===projectedBaselinePolicy.reject_incomplete_valuations &&
    simulation.require_complete &&
    (simulation.automatic_roster_policy ?? "mandatory_marginal_lineup_v1")==="mandatory_marginal_lineup_v1" &&
    (simulation.standings_fallback_seed ?? null)===projectedBaselinePolicy.standings_fallback_seed &&
    (!snapshot.live_scoring || snapshot.live_scoring.partial_week_simulation_required ||
      !simulation.use_observed_current_week_lineup);
}

function compatibleModel(summary: BackgroundBaselineResultSummary, {request}: ForecastRequest) {
  const {model_id,model_parameters,master_seed,first_path_index,requested_path_count} = summary.result.provenance;
  const parameters = new Map(model_parameters);
  return model_id==="provisional-independent-normal-v1:missing-projection-zero-v1" &&
    parameters.size===4 && model_parameters.length===4 &&
    parameters.get("missing_projection_outcome")==="deterministic-zero-v1" &&
    parameters.get("conditional_independence")===true &&
    parameters.get("base_stddev")===request.outcome_model.base_stddev_points &&
    parameters.get("projection_scale")===request.outcome_model.projection_scale &&
    master_seed===request.simulation.master_seed && first_path_index===request.simulation.first_path_index &&
    requested_path_count===request.simulation.path_count;
}

function useBaselineForecast(snapshot: SnapshotSummary, runs: readonly BackgroundRunRecord[],
  runListStatus: NonNullable<PlayoffRaceProps["runListStatus"]>, preferredRunId?: string | null,
  forecastRequests?: ReadonlyMap<string,ForecastRequest>) {
  const completed=useMemo(()=>runs.filter(run=>run.snapshot_id===snapshot.snapshot_id&&run.run_type==="baseline"&&run.status==="completed"&&run.result_available).sort((a,b)=>dateKey(b).localeCompare(dateKey(a))||a.run_id.localeCompare(b.run_id)),[runs,snapshot.snapshot_id]);
  const [pickedRun,setSelectedRun]=useState<string|null>(null);
  const eligible = forecastRequests
    ? completed.filter(run=>compatibleRequest(snapshot,forecastRequests.get(run.run_id))) : completed;
  const sharedForecast = forecastRequests!==undefined;
  const [rejected,setRejected] = useState<ReadonlyMap<string,string>>(()=>new Map());
  const recordKey = (record: BackgroundRunRecord) => JSON.stringify([record.run_id,record.request_sha256]);
  const chosen = eligible.find(run=>run.run_id===(pickedRun ?? preferredRunId));
  const selectedRecord = chosen ?? eligible.find(run=>!rejected.has(recordKey(run)));
  const rejectedRecord = eligible.find(run=>rejected.has(recordKey(run)));
  const rejection = rejectedRecord && rejected.get(recordKey(rejectedRecord));
  const selectedRun = selectedRecord?.run_id ?? null;
  const requestIdentity = selectedRecord?.request_sha256;
  const evidence = selectedRecord && forecastRequests?.get(selectedRecord.run_id);
  const [summary,setSummary]=useState<BackgroundBaselineResultSummary|null>(null);
  const [error,setError]=useState<string|null>(null);
  const [loading,setLoading]=useState(false);
  const checked = useRef<BackgroundBaselineResultSummary|null>(null);

  useEffect(()=>setSelectedRun(null),[preferredRunId]);
  useEffect(()=>{
    if(!sharedForecast)setSummary(null);
    setError(null);
    if(runListStatus!=="loaded" || !selectedRun) {
      setLoading(false);
      return;
    }
    const previous=checked.current;
    if(evidence && previous && !validateResult(previous,snapshot,selectedRun,requestIdentity) &&
        compatibleModel(previous,evidence)) {
      setSummary(previous);
      setLoading(false);
      return;
    }
    const controller=new AbortController();
    setLoading(true);
    void api.runResult(selectedRun,controller.signal).then(value=>{
      if(controller.signal.aborted)return;
      const problem=validateResult(value,snapshot,selectedRun,requestIdentity) ??
        (evidence && !compatibleModel(value,evidence)
          ? "The retained model or sampling configuration does not match the requested baseline." : null);
      if(problem) {
        if(sharedForecast && !pickedRun) {
          const key=JSON.stringify([selectedRun,requestIdentity]);
          setRejected(current=>new Map(current).set(key,problem));
        } else setError(problem);
        return;
      }
      checked.current=value;
      setSummary(value);
    }).catch(reason=>{
      if(!controller.signal.aborted)setError(reason instanceof ApiError?reason.message:"The retained result could not be read.");
    }).finally(()=>{
      if(!controller.signal.aborted)setLoading(false);
    });
    return()=>controller.abort();
  },[selectedRun,snapshot,runListStatus,requestIdentity,evidence,sharedForecast,pickedRun]);
  const matching=runs.filter(run=>run.snapshot_id===snapshot.snapshot_id&&run.run_type==="baseline");
  const visibleRecord = (forecastRequests && !pickedRun)
    ? eligible.find(run=>run.run_id===summary?.run.run_id) : selectedRecord;
  const activeSummary = runListStatus==="loaded" && summary && visibleRecord &&
    !validateResult(summary, snapshot, visibleRecord.run_id, visibleRecord.request_sha256) &&
    (!forecastRequests || compatibleModel(summary,forecastRequests.get(visibleRecord.run_id)!)) ? summary : null;
  return {completed:eligible, selectedRun, setSelectedRun, loading, error:error??rejection, activeSummary, matching, unverified:completed.length>eligible.length};
}

type Focus = { selected: number | undefined; onSelect: (id: number) => void };

const noRequests: ReadonlyMap<string,ForecastRequest> = new Map();

export function CommandCenter({layered=false, snapshot, projection, runs=noRuns, runListStatus="loaded", loadRuns, openCompatibleSimulation, modePreference, forecastRequests=noRequests}: OverviewProps) {
  const forecast = useBaselineForecast(snapshot, runs, runListStatus, undefined, forecastRequests);
  const projected = projection?.state.status==="available" &&
    projection.state.result.snapshot_id===snapshot.snapshot_id &&
    projection.state.result.canonical_sha256===snapshot.canonical_sha256 ? projection.state.result : null;
  const [localChoice, setLocalChoice] = useState<ForecastMode>();
  const choice = modePreference ? modePreference.choice : localChoice;
  const setChoice = modePreference?.select ?? setLocalChoice;
  const [focusedId, setFocusedId] = useState<number>();
  const [compactFocusExpanded,setCompactFocusExpanded] = useState(false);
  const [postseasonFocus, setPostseasonFocus] = useState(false);
  const modeControl = useRef<HTMLButtonElement>(null);
  const homeHeading = useRef<HTMLHeadingElement>(null);
  const focusTrigger = useRef<HTMLElement|null>(null);
  const team = snapshot.teams.find(item=>item.team_id===focusedId);
  const focus: Focus = {
    selected: team?.team_id,
    onSelect: id=> {
      setPostseasonFocus(false);
      setCompactFocusExpanded(false);
      focusTrigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      setFocusedId(current=>current===id?undefined:id);
    },
  };
  const bracketFocus: Focus = {
    ...focus,
    onSelect: id=>{
      focus.onSelect(id);
      setPostseasonFocus(true);
    },
  };
  const running = runListStatus==="loaded" && forecast.matching.some(run=>
    run.status==="queued" || run.status==="running" || run.status==="cancel_requested");
  useEffect(()=>{
    if(!running || !loadRuns)return;
    const controller = new AbortController();
    let timer: number;
    const poll = async()=>{
      try { await loadRuns(controller.signal); }
      catch { /* App reports the run-list failure. */ }
      if(!controller.signal.aborted)timer=window.setTimeout(()=>void poll(),1500);
    };
    timer=window.setTimeout(()=>void poll(),1500);
    return ()=>{ controller.abort(); window.clearTimeout(timer); };
  },[running,loadRuns]);

  const summary = choice!=="projected" ? forecast.activeSummary : null;
  const mode = summary && !layered ? "monte_carlo" : "projected";
  const probabilities = new Map(summary?.result.teams.map(row=>[row.team_id,row]));
  const ranks = new Map(projected?.teams.map(row=>[row.team_id,row]));
  const ordered = [...snapshot.teams].sort((a,b)=>
    (ranks.get(a.team_id)?.final_regular_rank??Infinity)-(ranks.get(b.team_id)?.final_regular_rank??Infinity) ||
    (a.standing??Infinity)-(b.standing??Infinity) || a.team_id-b.team_id);
  const teamForecast = team && probabilities.get(team.team_id);
  const teamProjection = team && ranks.get(team.team_id);
  const teamPath = team && projected?.postseason.filter(match=>
    match.bracket_type==="championship" &&
    (match.home_team_id===team.team_id || match.away_team_id===team.team_id));
  const standingsSeries = projected?.standings_series;
  const dismiss = ()=>{
    setFocusedId(undefined);
    if(focusTrigger.current?.isConnected)focusTrigger.current.focus();
    else (modeControl.current??homeHeading.current)?.focus();
  };

  return <section className="league-command" aria-labelledby="league-command-title"
    onKeyDown={event=>{if(event.key==="Escape" && team){event.stopPropagation();dismiss();}}}>
    <div className="command-heading">
      <h2 id="league-command-title" ref={layered?homeHeading:undefined} tabIndex={layered?-1:undefined}>League Command Center</h2>
      {!layered && <div className="command-modes" role="group" aria-label="Forecast mode">
        <button ref={modeControl} type="button" aria-pressed={(choice??mode)==="projected"} onClick={()=>setChoice("projected")}>Projected season</button>
        <button type="button" aria-pressed={(choice??mode)==="monte_carlo"} onClick={()=>setChoice("monte_carlo")}>Monte Carlo</button>
      </div>}
    </div>
    <div className="command-evidence">
      <p role="status">Showing {summary ? layered && projected ? "the projected season with Monte Carlo evidence" : "Monte Carlo" : projected ? "the projected season" : "no forecast"}.</p>
      {openCompatibleSimulation && <button className="workspace-action" type="button"
        onClick={openCompatibleSimulation}>Configure matching Monte Carlo</button>}
    </div>
    {projected && projected.unresolved_capabilities.length>0 &&
      <div className="analysis-warning">
        <AlertTriangle aria-hidden="true"/>
        <div>
          <strong role="status">Projected season available with analytical limitations.</strong>
          <details>
            <summary>Unresolved projected-season capabilities</summary>
            <ul>{[...new Set(projected.unresolved_capabilities)].map(capability=>
              <li key={capability}>{human(capability)}</li>)}</ul>
          </details>
        </div>
      </div>}
    {running && <p role="status">A baseline simulation is active. The available season outlook remains visible.</p>}
    {runListStatus==="loaded" && forecast.unverified && <p>Some retained runs have different or unverified forecast policies. Inspect them in Playoff Race.</p>}
    {forecast.loading && choice!=="projected" && <p role="status">Checking retained Monte Carlo evidence.</p>}
    {(forecast.error || (choice==="monte_carlo" && !summary && !forecast.loading)) &&
      <p role="status">{summary ? "Retained run issue." : "Monte Carlo forecast unavailable."} {forecast.error??"Select or request a compatible baseline."}</p>}
    <div className="command-canvas" role="group" aria-label="League forecast canvas">
      <section className="command-journey" aria-labelledby="command-journey">
        <h3 id="command-journey">Season Journey</h3>
        <SeasonJourney snapshot={snapshot} series={standingsSeries}
          monteCarlo={Boolean(summary)} {...focus}/>
        {team && !standingsSeries?.length && <p className="command-journey-focus">
          {team.display_name} / Observed rank {team.standing??"unavailable"}
        </p>}
        {team && <aside className={`command-team-focus ${postseasonFocus?"postseason-focus":""} ${compactFocusExpanded?"focus-expanded":""}`} aria-label="Team Focus" style={{borderColor:commandTeamColor(team.team_id)}}>
          <div className="command-focus-heading"><h3><TeamMark team={team}/> {team.display_name}</h3>
            <button type="button" onClick={dismiss} aria-label="Dismiss Team Focus">Close</button>
          </div>
          <p role="status">Observed record {team.wins}-{team.losses}-{team.ties} / Rank {team.standing??"unavailable"}</p>
          <button type="button" className="compact-focus-toggle" aria-expanded={compactFocusExpanded}
            aria-controls="command-focus-detail" onClick={()=>setCompactFocusExpanded(open=>!open)}>
            {compactFocusExpanded?"Hide team details":"Show team details"}
          </button>
          <div id="command-focus-detail" className={compactFocusExpanded?"compact-expanded":""}>
          {summary && <>
            {layered && <h4>Monte Carlo estimates</h4>}
            <TeamFocusMetric label="Playoff qualification" estimate={teamForecast?.playoff_qualification}/>
            <TeamFocusMetric label="Championship" estimate={teamForecast?.championship}/>
            <p className="focus-metric-context">Intervals describe Monte Carlo sampling uncertainty.</p>
            {teamForecast && teamForecast.final_placements.length>0 && <details className="journey-weekly">
              <summary>Final placement probabilities</summary>
              <ul>{[...teamForecast.final_placements].sort((a,b)=>a.placement-b.placement).map(row=><li key={row.placement}>
                <TeamFocusMetric label={ordinal(row.placement)} estimate={row.estimate}/>
              </li>)}</ul>
            </details>}
          </>}
          {(!summary || layered) && <>
            {layered && <h4>Projected season</h4>}
            <p>Projected finish {teamProjection?.final_regular_rank??"unavailable"}</p>
            {teamProjection?.championship_qualifier===true && <p>Qualified / Seed {teamProjection.postseason_seed??"unavailable"}</p>}
            {teamProjection?.championship_qualifier===false && <p>Outside projected championship field</p>}
            {teamProjection?.final_placement!=null && <p>Projected final placement {teamProjection.final_placement}</p>}
            {teamPath && teamPath.length>0 && <details className="journey-weekly">
              <summary>Projected championship path</summary>
              <ul>{teamPath.map(match=><li key={match.matchup_id}>
                Round {match.round_number}
                <b>{match.status==="bye" ? "Bye" : match.winner_team_id===null ? "Unresolved" :
                  match.winner_team_id===team.team_id ? "Win" : "Loss"}</b>
              </li>)}</ul>
            </details>}
          </>}
          {standingsSeries && standingsSeries.length>0 && <>
            {summary && <p className="bracket-context">Deterministic reference</p>}
            <JourneyTeamWeeks series={standingsSeries} teamId={team.team_id}/>
          </>}
          </div>
        </aside>}
      </section>
      <section className="command-race" aria-labelledby="command-race">
        <h3 id="command-race">Playoff Race</h3>
        {(!summary || layered) && projection && !projected && <ProjectionReadiness projection={projection}/>}
        <CommandPlayoffRace snapshot={snapshot} teams={ordered} ranks={ranks}
          probabilities={summary && !layered ? probabilities : null} enrichment={summary && layered ? probabilities : null} {...focus}/>
      </section>
    </div>
    <section className="command-postseason" aria-labelledby="command-postseason">
      <h3 id="command-postseason">Postseason Outlook</h3>
      {(!summary || layered) && <ProjectedBracket snapshot={snapshot} result={projected} {...bracketFocus}/>}
      {layered && projected?.champion_team_id!=null && <p className="bracket-context">
        Projected champion: {snapshot.teams.find(team=>team.team_id===projected.champion_team_id)?.display_name??"Unavailable"}
      </p>}
      {summary && <>
        <PrecisionNotice summary={summary}/>
        <div className="command-postseason-forecast">
          <section aria-labelledby="command-title-race">
            <h4 id="command-title-race">{layered?"Monte Carlo championship probability":"Championship probability"}</h4>
            <ProbabilityPlot teams={ordered} results={probabilities} compact {...bracketFocus}/>
          </section>
          {layered ? <details className="bracket-secondary">
            <summary>Monte Carlo final placement distribution</summary>
            <PlacementHeatmap teams={ordered} results={probabilities} compact {...bracketFocus}/>
          </details> : <section aria-labelledby="command-placements">
            <h4 id="command-placements">Final placement matrix</h4>
            <p className="bracket-context">Simulated finish probabilities; sampling precision is shown separately.</p>
            <PlacementHeatmap teams={ordered} results={probabilities} compact {...bracketFocus}/>
          </section>}
        </div>
        <RunDisclosure summary={summary}/>
        {!layered && <details className="bracket-secondary">
          <summary>Deterministic projected bracket reference</summary>
          <ProjectedBracket snapshot={snapshot} result={projected} {...bracketFocus}/>
        </details>}
      </>}
    </section>
    {summary && <p>Run {short(summary.run.run_id)} / Configuration {short(summary.result.provenance.simulation_config_sha256)}</p>}
    {runListStatus==="loaded" && forecast.completed.length>0 && <RunContext completed={forecast.completed}
      selected={forecast.selectedRun} onChange={id=>{forecast.setSelectedRun(id);if(!layered)setChoice("monte_carlo");}}/>}
    {runListStatus==="unavailable" && <p>Retained Monte Carlo results are unavailable. Use Retry run list to check again.</p>}
  </section>;
}
type ProjectedTeam = ProjectedBaselineResult["teams"][number];

function CommandPlayoffRace({snapshot, teams, ranks, probabilities, enrichment, selected, onSelect}: Focus & {
  snapshot: SnapshotSummary;
  teams: readonly TeamSummary[];
  ranks: ReadonlyMap<number,ProjectedTeam>;
  probabilities: ReadonlyMap<number,TeamProbabilityResult> | null;
  enrichment?: ReadonlyMap<number,TeamProbabilityResult> | null;
}) {
  const slots = snapshot.league_structure?.championship_qualifier_count;
  const fieldSize = slots != null && slots>0 && slots<=teams.length ? slots : null;
  const estimate = (team: TeamSummary) => probabilities?.get(team.team_id)?.playoff_qualification;
  const ordered = probabilities ? [...teams].sort((left,right)=>
    (estimate(right)?.probability??-1)-(estimate(left)?.probability??-1) || left.team_id-right.team_id
  ) : teams;
  return <>
    <p className="race-field">
      {fieldSize===null ? "Championship field size unavailable" : `${fieldSize} of ${teams.length} teams qualify for the championship bracket`}
    </p>
    <p className="race-context">{probabilities
      ? "Ranked by qualification probability. Field size is a reference."
      : "Ranked by projected finish. Qualification and seeds reflect modeled league rules."}</p>
    {probabilities && <div className="race-axis" aria-hidden="true"><span>0%</span><span>50%</span><span>100%</span></div>}
    <ol className="race-entries">
      {ordered.map((team,index)=>{
        const row=ranks.get(team.team_id);
        const metric=estimate(team);
        const probability=metric?.probability;
        const focus=selected===team.team_id;
        const interval=focus ? metric?.interval : null;
        const cutoff=fieldSize===index+1 && index+1<ordered.length &&
          (probabilities ? probability!=null : row?.final_regular_rank===fieldSize);
        return <li key={team.team_id} className={cutoff ? "race-field-cut":undefined}>
          <button type="button" className={`race-entry ${probabilities?"race-probability":""}`} style={{"--command-team-color":commandTeamColor(team.team_id)} as React.CSSProperties}
            aria-pressed={focus} onClick={()=>onSelect(team.team_id)}>
            {!probabilities && <span className="race-rank">
              <span className="sr-only">Projected rank </span>{row?.final_regular_rank??"Unavailable"}
            </span>}
            <TeamMark team={team}/>
            <span className="race-identity"><strong>{team.display_name}</strong>
              {!probabilities && <small>Observed rank {team.standing??"unavailable"}</small>}
            </span>
            {probabilities ? <>
              <span className="race-track" aria-hidden="true">
                {probability!=null && <span className="race-fill" style={{width:pct(probability)}}/>}
                {probability!=null && interval && <span className="race-interval"
                  style={{left:pct(interval.lower_probability),width:pct(interval.upper_probability-interval.lower_probability)}}/>}
              </span>
              <strong className="race-value">{probability==null ? "Unavailable" : racePercent(probability)}</strong>
              {focus && probability!=null && <span className="race-detail">
                {interval ? `${racePercent(interval.lower_probability)} to ${racePercent(interval.upper_probability)} sampling interval` : "Sampling interval unavailable"}
                {metric && ` / ${metric.successes.toLocaleString()} of ${metric.trials.toLocaleString()} qualifying paths`}
                {metric && !metric.precision_reached && " / Precision target pending"}
              </span>}
            </> : <span className={`race-seed ${row?.championship_qualifier===true?"race-qualified":""}`}>
              {row?.championship_qualifier===true
                ? row.postseason_seed==null ? "Qualified / seed unavailable" : `Seed ${row.postseason_seed} / Qualified`
                : row?.championship_qualifier===false
                  ? row.postseason_seed==null ? "Outside championship field" : `Seed ${row.postseason_seed} / Outside championship field`
                  : "Qualification unavailable"}
              {enrichment && <small className="race-enrichment">
                MC qualification: {shortProbability(enrichment.get(team.team_id)?.playoff_qualification.probability)}
              </small>}
            </span>}
          </button>
          {cutoff && <span className="race-cut-label">{fieldSize} championship slots / field-size reference</span>}
        </li>;
      })}
    </ol>
  </>;
}

function racePercent(value: number) {
  return new Intl.NumberFormat(undefined,{style:"percent",maximumFractionDigits:10}).format(value);
}

function RunContext({completed,selected,onChange}:{completed:readonly BackgroundRunRecord[];selected:string|null;onChange:(id:string)=>void}){return <section className="analysis-context" aria-label="Analysis context"><div><span className="overline">Analysis source</span><strong>{completed.length?`${completed.length} completed baseline run${completed.length===1?"":"s"}`:"No usable completed baseline"}</strong><small>Newest retained result is selected by default. Selection never launches a run.</small></div>{completed.length>0&&<label><span>Completed run</span><select value={selected??""} onChange={event=>onChange(event.target.value)}>{completed.map(run=><option key={run.run_id} value={run.run_id}>{formatDate(run.finished_at_utc??run.created_at_utc)} · {short(run.run_id)}</option>)}</select></label>}</section>}
function AnalyticsDashboard({snapshot,summary}:{snapshot:SnapshotSummary;summary:BackgroundBaselineResultSummary}){const teams=useMemo(()=>[...snapshot.teams].sort((a,b)=>(a.standing??999)-(b.standing??999)||a.team_id-b.team_id),[snapshot]);const results=useMemo(()=>new Map(summary.result.teams.map(team=>[team.team_id,team])),[summary]);const [teamId,setTeamId]=useState(teams[0]?.team_id);useEffect(()=>setTeamId(current=>teams.some(team=>team.team_id===current)?current:teams[0]?.team_id),[snapshot.snapshot_id,teams]);const selected=teams.find(team=>team.team_id===teamId),selectedResult=teamId===undefined?undefined:results.get(teamId);return <><PrecisionNotice summary={summary}/><div className="analytics-grid"><section className="analytics-panel championship-panel" aria-labelledby="championship-title"><PanelTitle eyebrow="Title race" title="Championship probability" id="championship-title" note="Engine-supplied interval whiskers"/><ProbabilityPlot teams={teams} results={results} selected={teamId} onSelect={setTeamId}/></section><aside className="analytics-panel selected-team" aria-live="polite"><span className="overline">Selected team</span><div className="team-identity"><TeamMark team={selected}/><div><h2>{selected?.display_name??"Unavailable"}</h2><p>{selected?`${selected.wins}–${selected.losses}${selected.ties?`–${selected.ties}`:""} · ${selected.points_for.toFixed(1)} PF`:"No matching team"}</p></div></div><Metric label="Championship" estimate={selectedResult?.championship}/><Metric label="Playoff qualification" estimate={selectedResult?.playoff_qualification}/><div className="selected-observed"><span>Observed standing <b>{selected?.standing??"—"}</b></span><span>Playoff seed <b>{selected?.playoff_seed??"—"}</b></span></div><p className="integrity-note"><ShieldCheck/> Forecast probabilities and observed snapshot facts remain explicitly separate.</p></aside></div><section className="analytics-panel playoff-panel" aria-labelledby="playoff-title"><PanelTitle eyebrow="Qualification field" title="Playoff probability bands" id="playoff-title" note="Bands include supplied interval markers"/><PlayoffBands teams={teams} results={results} selected={teamId} onSelect={setTeamId}/></section><section className="analytics-panel heatmap-panel" aria-labelledby="placement-title"><PanelTitle eyebrow="Outcome distribution" title="Final placement matrix" id="placement-title" note="Exact values remain visible"/><PlacementHeatmap teams={teams} results={results} selected={teamId} onSelect={setTeamId}/></section><RunDisclosure summary={summary}/></>}
function PrecisionNotice({summary}:{summary:BackgroundBaselineResultSummary}){const r=summary.result,metricPrecisionMissing=r.teams.some(team=>![team.championship,team.playoff_qualification,...team.final_placements.map(item=>item.estimate)].every(metric=>metric.precision_reached));const notices=[r.incomplete_paths>0&&`${r.incomplete_paths.toLocaleString()} simulation paths were incomplete`,r.incomplete_capabilities.length>0&&`${r.incomplete_capabilities.length} analytical capabilities were incomplete`,!r.league_wide_precision_reached&&"the league-wide precision target was not reached",metricPrecisionMissing&&"one or more metric-level precision targets were not reached"].filter(Boolean) as string[];return <>{notices.length>0&&<div className="analysis-warning precision-warning" role="status"><AlertTriangle/><div><strong>Precision or coverage qualification</strong><span>Execution completed, but {notices.join("; ")}. Review technical details below.</span><small>Confidence intervals describe Monte Carlo sampling uncertainty, not outcome-model uncertainty.</small></div></div>}</>;}
const overviewPercent = new Intl.NumberFormat(undefined,{style:"percent",maximumSignificantDigits:3});
function shortProbability(value: number | null | undefined) {
  return value==null ? "Unavailable" : overviewPercent.format(value);
}

function ProbabilityPlot({teams,results,selected,onSelect,compact=false}: Focus & {
  teams:readonly TeamSummary[];
  results:ReadonlyMap<number,TeamProbabilityResult>;
  compact?:boolean;
}) {
  const ordered=[...teams].sort((a,b)=>
    (results.get(b.team_id)?.championship.probability??-1)-(results.get(a.team_id)?.championship.probability??-1) || a.team_id-b.team_id);
  return <div className={`probability-plot ${compact?"postseason-title-race":""}`}>
    {ordered.map(team=>{
      const estimate=results.get(team.team_id)?.championship, p=estimate?.probability, interval=estimate?.interval;
      return <button key={team.team_id} className={selected===team.team_id?"selected":""}
        onClick={()=>onSelect(team.team_id)} aria-pressed={selected===team.team_id}
        aria-label={`${team.display_name}: championship ${metricDescription(estimate)}`}
        style={compact?{"--postseason-accent":commandTeamColor(team.team_id)} as React.CSSProperties:undefined}>
        <TeamMark team={team}/><strong>{team.display_name}</strong>
        <span className="probability-track">{p!=null&&<>
          <i className="dot" style={{left:pct(p)}}/>
          {interval&&<i className="interval" style={{left:pct(interval.lower_probability),
            width:pct(interval.upper_probability-interval.lower_probability)}}/>}
        </>}</span>
        <b>{compact&&p!=null?overviewPercent.format(p):percent(p)}
          {estimate&&!estimate.precision_reached&&<small>Precision pending</small>}
        </b>
      </button>;
    })}
    <div className="probability-axis"><span>0%</span><span>50%</span><span>100%</span></div>
  </div>;
}
function PlayoffBands({teams,results,selected,onSelect}:{teams:readonly TeamSummary[];results:ReadonlyMap<number,TeamProbabilityResult>;selected:number|undefined;onSelect:(id:number)=>void}){const ordered=[...teams].sort((a,b)=>(results.get(b.team_id)?.playoff_qualification.probability??-1)-(results.get(a.team_id)?.playoff_qualification.probability??-1)||a.team_id-b.team_id);return <div className="playoff-bands">{ordered.map(team=>{const estimate=results.get(team.team_id)?.playoff_qualification,p=estimate?.probability,interval=estimate?.interval;return <button key={team.team_id} onClick={()=>onSelect(team.team_id)} className={selected===team.team_id?"selected":""} aria-pressed={selected===team.team_id} aria-label={`${team.display_name}: playoff qualification ${metricDescription(estimate)}`}><span><TeamMark team={team}/><strong>{team.display_name}</strong></span><span className="band">{p!==null&&p!==undefined&&<i className="band-fill" style={{width:pct(p)}}/>}{interval&&<i className="band-interval" style={{left:pct(interval.lower_probability),width:pct(interval.upper_probability-interval.lower_probability)}}/>}{p===null||p===undefined?<em>Unavailable</em>:<b>{percent(p)}{!estimate?.precision_reached&&<small>Precision pending</small>}</b>}{p!==null&&p!==undefined&&!interval&&<span className="interval-missing">Interval unavailable</span>}</span></button>})}</div>}
function PlacementHeatmap({teams,results,selected,onSelect,compact=false}: Focus & {
  teams:readonly TeamSummary[];
  results:ReadonlyMap<number,TeamProbabilityResult>;
  compact?:boolean;
}) {
  const places=[...new Set([...results.values()].flatMap(team=>team.final_placements.map(item=>item.placement)))].sort((a,b)=>a-b);
  if(!places.length)return <p>Final placement probabilities are unavailable.</p>;
  return <>
    {compact && <p className="bracket-context">Darker cells indicate higher probability. Hatched cells are unavailable.</p>}
    <div className={`placement-scroll ${compact?"postseason-placement":""}`}
      role={compact?"region":undefined} aria-label={compact?"Placement probabilities by team":undefined} tabIndex={compact?0:undefined}>
      <div className="placement-matrix" style={compact?{"--placements":places.length} as React.CSSProperties:
        {gridTemplateColumns:`minmax(130px,1.4fr) repeat(${places.length},minmax(48px,1fr))`}}>
        <span className="matrix-corner">Team / finish</span>
        {places.map(place=><strong key={place}>{compact?<><span aria-hidden="true">{place}</span><span className="sr-only">{ordinal(place)}</span></>:ordinal(place)}</strong>)}
        {teams.map(team=><PlacementRow key={team.team_id} team={team} result={results.get(team.team_id)}
          places={places} selected={selected===team.team_id} onSelect={onSelect} compact={compact}/>)}
      </div>
    </div>
    <details className="exact-table"><summary>Accessible exact placement table</summary>
      <div className={compact?"postseason-exact-scroll":undefined} role={compact?"region":undefined}
        aria-label={compact?"Exact placement values by team":undefined} tabIndex={compact?0:undefined}>
        <table><thead><tr><th scope="col">Team</th>{places.map(place=><th key={place} scope="col">{ordinal(place)}</th>)}</tr></thead>
        <tbody>{teams.map(team=><tr key={team.team_id}><th scope="row">{team.display_name}</th>{places.map(place=>
          <td key={place}>{percent(results.get(team.team_id)?.final_placements.find(item=>item.placement===place)?.estimate.probability)}</td>)}</tr>)}</tbody></table>
      </div>
    </details>
  </>;
}

function PlacementRow({team,result,places,selected,onSelect,compact}: {
  team:TeamSummary; result:TeamProbabilityResult|undefined; places:readonly number[];
  selected:boolean; onSelect:(id:number)=>void; compact:boolean;
}) {
  const accent=commandTeamColor(team.team_id);
  return <>
    <button className={`matrix-team ${selected?"selected":""}`} onClick={()=>onSelect(team.team_id)} aria-pressed={selected}
      style={compact?{"--postseason-accent":accent} as React.CSSProperties:undefined}>
      <TeamMark team={team}/><span>{team.display_name}</span>
    </button>
    {places.map(place=>{
      const p=result?.final_placements.find(item=>item.placement===place)?.estimate.probability;
      const label=`${team.display_name}, ${ordinal(place)}: ${percent(p)}`;
      return <span key={place} className={`heat-cell ${p==null?"unavailable":""} ${selected&&compact?"focused":""}`}
        style={{"--heat":p!=null?String(.08+p*.82):undefined,"--postseason-accent":compact?accent:undefined} as React.CSSProperties}
        aria-label={label} title={label}>
        <span className={compact?"placement-overview-value":undefined}>{compact&&p!=null?overviewPercent.format(p):percent(p)}</span>
      </span>;
    })}
  </>;
}
function RunDisclosure({summary}:{summary:BackgroundBaselineResultSummary}){const r=summary.result;return <details className="run-disclosure"><summary><BarChart3/> Analysis precision, provenance, and limitations</summary><p>Execution status, capability completeness, and Monte Carlo precision are independent. Confidence intervals quantify sampling uncertainty only; model evidence and calibration limitations remain separate.</p><div className="run-facts"><span><b>Completed</b> execution</span><span><b>{r.completed_paths.toLocaleString()} / {r.requested_paths.toLocaleString()}</b> completed paths</span><span><b>{r.incomplete_paths.toLocaleString()}</b> incomplete paths</span><span><b>{r.league_wide_precision_reached?"Reached":"Not reached"}</b> league-wide precision</span><span><b>{r.teams.filter(team=>[team.championship,team.playoff_qualification,...team.final_placements.map(item=>item.estimate)].some(metric=>!metric.precision_reached)).length}</b> teams with pending metric precision</span><span><b>{human(r.stopping_reason)}</b> stop reason</span></div><dl><div><dt>Outcome model</dt><dd>{r.provenance.model_id}</dd></div><div><dt>Master seed</dt><dd>{r.provenance.master_seed}</dd></div><div><dt>Simulation identity</dt><dd>{short(r.provenance.engine_run_identity_sha256)}</dd></div><div><dt>Configuration</dt><dd>{short(r.provenance.simulation_config_sha256)}</dd></div></dl>{r.incomplete_capabilities.length>0&&<div><strong>Incomplete capabilities</strong><ul>{r.incomplete_capabilities.map(([capability,week])=><li key={`${capability}-${week}`}>{human(capability)} at scoring week {week}</li>)}</ul></div>}{r.limitations.length>0&&<div><strong>Outcome-model and evidence limitations</strong><ul>{r.limitations.map(item=><li key={item}>{item}</li>)}</ul></div>}</details>}
function NoAnalysis({runs}:{runs:readonly BackgroundRunRecord[]}){const active=runs.filter(run=>["queued","running","cancel_requested"].includes(run.status)),terminal=runs.filter(run=>["failed","cancelled","interrupted"].includes(run.status));return <><AnalyticsState icon={<Trophy/>} title={active.length?"Baseline analysis in progress":"No completed baseline analysis"} body={active.length?`${active.length} matching run${active.length===1?" is":"s are"} active. This page will not start or substitute analysis.`:"No retained completed baseline result matches this canonical snapshot."}/>{terminal.length>0&&<p className="run-history-note">{terminal.length} matching run{terminal.length===1?"":"s"} ended without a usable result: {[...new Set(terminal.map(run=>run.status))].join(", ")}.</p>}</>}
function ObservedSnapshot({snapshot}:{snapshot:SnapshotSummary}){const teams=[...snapshot.teams].sort((a,b)=>(a.standing??999)-(b.standing??999)||a.team_id-b.team_id);return <section className="analytics-panel observed-fallback" aria-labelledby="observed-title"><PanelTitle eyebrow="Observed snapshot" title="Current league standings" id="observed-title" note="No forecast values are implied"/><div className="observed-list">{teams.map(team=><div key={team.team_id}><span>{team.standing??"—"}</span><TeamMark team={team}/><strong>{team.display_name}</strong><span>{team.wins}–{team.losses}</span><b>{team.points_for.toFixed(1)} PF</b></div>)}</div></section>}
function AnalyticsState({icon,title,body}:{icon:React.ReactNode;title:string;body:string}){return <section className="analytics-state">{icon}<div><span className="overline">Analytics status</span><h2>{title}</h2><p>{body}</p></div></section>}
function PanelTitle({eyebrow,title,id,note}:{eyebrow:string;title:string;id:string;note:string}){return <header className="section-heading"><div><span className="overline">{eyebrow}</span><h2 id={id}>{title}</h2></div><small>{note}</small></header>}
function TeamMark({team}:{team:TeamSummary|undefined}){const name=team?.display_name??"TBD";return <span className={`team-mark command-team-mark accent-${team?team.team_id%4:0}`} style={team?{"--command-team-color":commandTeamColor(team.team_id)} as React.CSSProperties:undefined} aria-hidden="true"><i/>{name.split(/\s+/).map(part=>part[0]).join("").slice(0,3).toUpperCase()}</span>}
function TeamFocusMetric({label,estimate}:{label:string;estimate:ProbabilityValue|undefined}) {
  const probability=estimate?.probability;
  const interval=estimate?.interval;
  return <div className="focus-probability">
    <span>{label}</span>
    <strong>{probability==null?"Unavailable":overviewPercent.format(probability)}</strong>
    <p>{interval ? `Sampling interval: ${percent(interval.lower_probability)} to ${percent(interval.upper_probability)}`
      : "Sampling interval unavailable"}</p>
    {estimate && !estimate.precision_reached && <p className="focus-precision">Precision target not reached</p>}
    {probability!=null && <details>
      <summary>Exact {label.toLowerCase()} values</summary>
      <dl>
        <dt>Estimate</dt><dd>{percent(probability)} (probability {String(probability)})</dd>
        {interval && <><dt>Interval endpoints (probabilities)</dt>
          <dd>{String(interval.lower_probability)} to {String(interval.upper_probability)}</dd></>}
      </dl>
    </details>}
  </div>;
}

function Metric({label,estimate}:{label:string;estimate:ProbabilityValue|undefined}){return <div className="forecast-metric"><span>{label}</span><strong>{percent(estimate?.probability)}</strong><small>{estimate?.interval?`${percent(estimate.interval.lower_probability)}–${percent(estimate.interval.upper_probability)} simultaneous interval`:"Interval unavailable"}{estimate&&!estimate.precision_reached?" · Precision target not reached":""}</small></div>}
function validateResult(value:BackgroundBaselineResultSummary,snapshot:SnapshotSummary,runId:string,requestIdentity:string|undefined){if(value.api_schema_version!=="1.0"||value.result.api_schema_version!=="1.0")return "This retained result uses an unsupported schema version.";if(value.run.run_id!==runId||value.run.run_type!=="baseline"||value.run.status!=="completed"||!value.run.result_available||value.run.request_sha256!==requestIdentity)return "The retained result identity does not match the selected baseline run.";if(value.run.snapshot_id!==snapshot.snapshot_id||value.result.provenance.snapshot_id!==snapshot.snapshot_id)return "The retained result belongs to a different snapshot.";if(value.result.provenance.canonical_sha256!==snapshot.canonical_sha256)return "The retained result canonical identity does not match the active snapshot.";if(value.result.teams.some(team=>!snapshot.teams.some(item=>item.team_id===team.team_id)))return "The retained result contains a team outside the active snapshot.";return null}
function dateKey(run:BackgroundRunRecord){return run.finished_at_utc??run.created_at_utc}
function percent(value:number|null|undefined){return value===null||value===undefined?"Unavailable":racePercent(value)}
function metricDescription(estimate:ProbabilityValue|undefined){if(!estimate||estimate.probability===null)return "estimate unavailable";const interval=estimate.interval?`, interval ${percent(estimate.interval.lower_probability)} to ${percent(estimate.interval.upper_probability)}`:", interval unavailable";return `${percent(estimate.probability)}${interval}, precision target ${estimate.precision_reached?"reached":"not reached"}`}
function pct(value:number){return `${Math.max(0,Math.min(1,value))*100}%`}
function ordinal(value:number){const mod=value%100;return `${value}${mod>=11&&mod<=13?"th":value%10===1?"st":value%10===2?"nd":value%10===3?"rd":"th"}`}
function human(value:string){return value.replaceAll("_"," ").replace(/\b\w/g,letter=>letter.toUpperCase())}
function short(value:string){return value.length>16?`${value.slice(0,8)}…${value.slice(-6)}`:value}
function formatDate(value:string){return new Intl.DateTimeFormat(undefined,{dateStyle:"medium",timeStyle:"short"}).format(new Date(value))}
