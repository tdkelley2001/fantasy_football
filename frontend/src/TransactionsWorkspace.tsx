import {useEffect,useLayoutEffect, useRef, useState} from "react";
import {ArrowLeftRight, Search} from "lucide-react";
import {SimulationCenter} from "./SimulationCenter";
import type {api} from "./lib/api";
import {OpportunityExplorer} from "./OpportunityExplorer";
import {TradeLab, type DiscoveryDraft} from "./TradeLab";
import type {BackgroundRunRecord, BackgroundManualScenarioResultSummary, SnapshotSummary} from "./types/api";

export function TransactionsWorkspace({snapshot, view, managerTeamId, runs, runListStatus, preferredRunId, navigate, advancedInitially, loadRuns, openResult}: {
  snapshot: SnapshotSummary;
  view: "discover" | "evaluate" | "prior";
  managerTeamId?: number;
  runs: readonly BackgroundRunRecord[];
  runListStatus: "loading" | "loaded" | "unavailable";
  preferredRunId?: string | null;
  navigate: (view: "discover" | "evaluate" | "prior") => void;
  advancedInitially?: boolean;
  loadRuns: typeof api.runs;
  openResult: (run: BackgroundRunRecord) => void;
}) {
  const [tradeTeams, setTradeTeams] = useState<ReadonlyMap<string, readonly number[]>>(()=>new Map());
  const rememberTrade = ({run,result}: BackgroundManualScenarioResultSummary) =>
    setTradeTeams(current=>new Map(current).set(run.run_id,result.affected_team_ids));
  const [offer, setOffer] = useState<DiscoveryDraft>();
  const advanced = useRef<HTMLDetailsElement>(null);
  const reviewLink = useRef<HTMLButtonElement>(null);
  const discoveryTrigger = useRef<HTMLButtonElement>(null);
  const handoff = (draft: DiscoveryDraft, trigger: HTMLButtonElement) => {
    discoveryTrigger.current = trigger;
    setOffer(draft);
    navigate("evaluate");
  };
  useLayoutEffect(() => {
    if (view === "evaluate" && offer) reviewLink.current?.focus();
    if (view === "discover" && discoveryTrigger.current?.isConnected) {
      discoveryTrigger.current.focus();
      discoveryTrigger.current = null;
    }
  }, [view, offer]);

  useEffect(()=>{
    if (view!=="prior") return;
    const controller = new AbortController();
    void loadRuns(controller.signal).catch(()=>{ /* The shell reports run-list failures. */ });
    return ()=>controller.abort();
  },[view,loadRuns]);
  const manager = snapshot.teams.find(team => team.team_id === managerTeamId);
  const prior = runs.filter(run=>run.snapshot_id===snapshot.snapshot_id &&
    (run.run_type==="manual_scenario" || run.run_type==="action_search") && run.status==="completed")
    .sort((a,b)=>(b.finished_at_utc??b.created_at_utc).localeCompare(a.finished_at_utc??a.created_at_utc));
  const retained = runListStatus==="loaded" ? prior.find(run=>run.run_id===preferredRunId && run.result_available) : undefined;
  return <article className="transactions-workspace">
    <header className="transactions-mast">
      <div>
        {manager && <p className="eyebrow">{manager.display_name}</p>}
        <h1>Transactions</h1>
        <p>Find an exchange, inspect its impact, or build your own.</p>
      </div>
      <p className="transaction-readonly">Hypothetical analysis. War Room never submits a move to ESPN.</p>
    </header>
    <nav className="transaction-views" aria-label="Transactions views">
      <button type="button" aria-current={view==="discover"?"page":undefined} onClick={()=>navigate("discover")}>
        <Search aria-hidden="true"/>Discover
      </button>
      <button type="button" ref={reviewLink} aria-current={view==="evaluate"?"page":undefined} onClick={()=>navigate("evaluate")}>
        <ArrowLeftRight aria-hidden="true"/>Evaluate
      </button>
      <button type="button" aria-current={view==="prior"?"page":undefined} onClick={()=>navigate("prior")}>Prior analyses</button>
    </nav>
    <div hidden={view!=="discover"}>
      <OpportunityExplorer snapshot={snapshot} runs={runs} runListStatus={runListStatus} embedded
        preferredRunId={retained?.run_type==="action_search"?preferredRunId:undefined} managerTeamId={managerTeamId} onHandoff={handoff}
        advancedSearch={<details className="transaction-search-disclosure" ref={advanced} open={advancedInitially || undefined}>
          <summary>Find more types of moves</summary>
          <p>Search selected trades, acquisitions, and supported sequences. A supported full-week start is required.</p>
          <SimulationCenter inDiscover actionSearchInitially initialRequestingTeam={managerTeamId}
            snapshot={snapshot} runs={runs} runListStatus={runListStatus} loadRuns={loadRuns} openResult={run=>{
              if (advanced.current) advanced.current.open=false;
              if (view==="discover") openResult(run);
            }}/>
        </details>}/>
    </div>
    {view==="prior" && <section aria-labelledby="prior-title" className="transaction-prior">
      <h2 id="prior-title">Prior analyses</h2>
      {runListStatus==="loading" ? <p role="status">Loading prior analyses.</p> :
        runListStatus==="unavailable" ? <p role="status">Prior analyses are unavailable. Use Retry run list to check again.</p> :
        prior.length===0 ? <p>No completed transaction analyses in the available history for this snapshot.</p> :
        <ul>{prior.map(run=>{
          const title=run.run_type==="manual_scenario"?"Trade comparison":"Opportunity search";
          const teams = tradeTeams.get(run.run_id)?.flatMap(id=>{
            const team = snapshot.teams.find(item=>item.team_id===id);
            return team ? [team.display_name] : [];
          });
          return <li key={run.run_id}>
            <div><strong>{title}</strong><p>{new Date(run.finished_at_utc??run.created_at_utc).toLocaleString()} / {run.run_id.slice(0,8)}</p>
              {Boolean(teams?.length) && <p>Affected teams: {teams!.join(", ")}</p>}</div>
            {run.result_available ? <button type="button" className="workspace-action"
              onClick={()=>openResult(run)}>Open {title.toLowerCase()}</button> : <span>Result unavailable</span>}
          </li>;
        })}</ul>}
    </section>}
    <div hidden={view!=="evaluate"}>
      <TradeLab onValidatedResult={rememberTrade} snapshot={snapshot} embedded managerTeamId={managerTeamId}
        preferredRunId={retained?.run_type==="manual_scenario"?preferredRunId:undefined} discoveryDraft={offer}
        clearDiscoveryDraft={()=>setOffer(undefined)}/>
    </div>
  </article>;
}
