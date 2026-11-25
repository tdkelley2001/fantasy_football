import {useLayoutEffect, useRef, useState} from "react";
import {ArrowLeftRight, Search} from "lucide-react";
import {OpportunityExplorer} from "./OpportunityExplorer";
import {TradeLab, type DiscoveryDraft} from "./TradeLab";
import type {BackgroundRunRecord, SnapshotSummary} from "./types/api";

export function TransactionsWorkspace({snapshot, view, managerTeamId, runs, runListStatus, preferredRunId, navigate, openSimulation}: {
  snapshot: SnapshotSummary;
  view: "discover" | "evaluate";
  managerTeamId?: number;
  runs: readonly BackgroundRunRecord[];
  runListStatus: "loading" | "loaded" | "unavailable";
  preferredRunId?: string | null;
  navigate: (view: "discover" | "evaluate") => void;
  openSimulation: () => void;
}) {
  const [offer, setOffer] = useState<DiscoveryDraft>();
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

  const manager = snapshot.teams.find(team => team.team_id === managerTeamId);
  const retained = runs.find(run=>run.run_id===preferredRunId);
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
      <button type="button" className="transaction-configure" onClick={openSimulation}>Configure simulations and searches</button>
    </nav>
    <div hidden={view!=="discover"}>
      <OpportunityExplorer snapshot={snapshot} runs={runs} runListStatus={runListStatus} embedded
        preferredRunId={retained?.run_type==="action_search"?preferredRunId:undefined} managerTeamId={managerTeamId} onHandoff={handoff}/>
    </div>
    <div hidden={view!=="evaluate"}>
      <TradeLab snapshot={snapshot} embedded managerTeamId={managerTeamId}
        preferredRunId={retained?.run_type==="manual_scenario"?preferredRunId:undefined} discoveryDraft={offer}
        clearDiscoveryDraft={()=>setOffer(undefined)}/>
    </div>
  </article>;
}
