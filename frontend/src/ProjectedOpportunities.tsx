import {useEffect, useRef, useState} from "react";
import {api} from "./lib/api";
import {ProjectedTradeResult} from "./ProjectedTradeResult";
import {replayDraft, type DiscoveryDraft, type DraftTransfer} from "./TradeLab";
import type {ProjectedOpportunityResult, SnapshotSummary} from "./types/api";

type Candidate = ProjectedOpportunityResult["candidates"][number];

function sameTransfers(expected: readonly DraftTransfer[], actual: Candidate["explicit_changes"]) {
  return expected.length === actual.length && expected.every(move => actual.some(row =>
    row.player_id===move.player_id && row.from_team_id===move.from_team_id && row.to_team_id===move.to_team_id));
}

export function discoveryDraft(
  snapshot: SnapshotSummary, candidate: Candidate, team: number, counterparty: number,
): DiscoveryDraft | string {
  if (candidate.limitation || candidate.evaluation_index === null)
    return "This candidate did not complete a projected evaluation.";
  const action = candidate.actions?.[0];
  if (candidate.actions?.length!==1 || !action || action.action_index!==1 ||
      action.action_type!=="trade" || action.conditional || action.team_id!==team ||
      action.counterparty_team_id!==counterparty || action.acquired_player_id!==null ||
      action.dropped_player_id!==null || !action.outgoing_player_ids.length || !action.incoming_player_ids.length)
    return "The ordered intent cannot be reproduced as a supported two-team exchange.";
  const transfers: DraftTransfer[] = [
    ...action.outgoing_player_ids.map(player_id=>({player_id,from_team_id:team,to_team_id:counterparty})),
    ...action.incoming_player_ids.map(player_id=>({player_id,from_team_id:counterparty,to_team_id:team})),
  ];
  if (!sameTransfers(transfers,candidate.explicit_changes)) return "The action and ownership changes disagree.";
  const timed = snapshot.live_scoring;
  const timing = candidate.timeline[0];
  if (timed) {
    const eligibility = new Map(timed.player_earliest_trade_weeks);
    if (candidate.timeline.length!==1 || !timing || !sameTransfers(transfers,timing.transfers) ||
        !timed.supported_trade_weeks?.includes(timing.scoring_week) ||
        transfers.some(move=>!eligibility.has(move.player_id) || eligibility.get(move.player_id)!>timing.scoring_week))
      return "The effective week cannot be verified for this exchange on the active snapshot.";
  } else if (candidate.timeline.length) {
    return "This snapshot cannot reproduce the candidate's effective timeline.";
  }
  const step = {step_id:`discovery-${candidate.candidate_id}`, transfers,
    ...(timing && {timing:"selected" as const, selectedWeek:timing.scoring_week})};
  try {
    replayDraft(snapshot,[step]);
  } catch {
    return "The candidate's player ownership differs from the active roster.";
  }
  return {teamId:team,counterpartyId:counterparty,step};
}

export function ProjectedOpportunities({snapshot, managerTeamId, onHandoff}: {
  snapshot: SnapshotSummary;
  managerTeamId?: number;
  onHandoff?: (draft: DiscoveryDraft, trigger: HTMLButtonElement) => void;
}) {
  const [team, setTeam] = useState(managerTeamId ?? snapshot.teams[0]?.team_id ?? 0);
  const [counterparty, setCounterparty] = useState(snapshot.teams.find(row=>row.team_id!==team)?.team_id ?? 0);
  const [result, setResult] = useState<ProjectedOpportunityResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);
  const clear = () => {
    active.current?.abort();
    setResult(null);
    setError(null);
    setBusy(false);
  };
  async function search() {
    clear();
    const request = new AbortController();
    active.current = request;
    setBusy(true);
    try {
      const response = await api.projectedOpportunities(snapshot, team, counterparty, request.signal);
      if (request.signal.aborted) return;
      if (response.snapshot_id !== snapshot.snapshot_id || response.canonical_sha256 !== snapshot.canonical_sha256)
        throw new Error("The projected search belongs to a different snapshot.");
      if ([response.baseline,...response.evaluations].some(output=>output &&
          (output.season.snapshot_id!==snapshot.snapshot_id || output.season.canonical_sha256!==snapshot.canonical_sha256)))
        throw new Error("A projected comparison belongs to a different snapshot.");
      setResult(response);
    } catch (reason) {
      if (!request.signal.aborted) setError(reason instanceof Error ? reason.message : "Projected search unavailable.");
    } finally {
      if (!request.signal.aborted) setBusy(false);
    }
  }
  const player = (id: number) => snapshot.players.find(row => row.player_id === id)?.display_name ?? String(id);
  const rank = (season: NonNullable<ProjectedOpportunityResult["baseline"]>, id: number) =>
    season.season.teams.find(row=>row.team_id===id)?.final_regular_rank ?? "Unavailable";
  return <section className="analytics-panel" aria-labelledby="projected-opportunities-title">
    <h2 id="projected-opportunities-title">Projected trade opportunities</h2>
    <p>Compare up to six one-for-one exchanges against the unchanged season.</p>
    <div className="transaction-search"><label>Requesting team <select value={team} onChange={event => {clear(); setTeam(Number(event.target.value));}}>
      {snapshot.teams.map(row => <option key={row.team_id} value={row.team_id}>{row.display_name}</option>)}
    </select></label>
    <label>Counterparty <select value={counterparty} onChange={event => {clear(); setCounterparty(Number(event.target.value));}}>
      {snapshot.teams.map(row => <option key={row.team_id} value={row.team_id}>{row.display_name}</option>)}
    </select></label>
    <button className="primary-button" onClick={() => void search()} disabled={busy || !team || !counterparty || team === counterparty}>
      {busy ? "Evaluating exchanges..." : "Find projected trades"}
    </button></div>
    {error && <p role="alert">{error}</p>}
    {result && <>
      <p role="status">{result.candidates.length} retained candidates from {result.generated_candidates} generated.
        {" "}{result.evaluations.length} distinct season evaluations.
        {!result.candidate_coverage_complete && ` Candidate coverage incomplete. ${result.truncation_reason ?? ""}`}
        {!result.evaluation_coverage_complete && " Evaluation coverage incomplete."}
      </p>
      <p>Each comparison shows one projected outcome. No probability ranking is calculated.</p>
      {result.candidates.map(candidate => {
        const season = candidate.evaluation_index === null ? null : result.evaluations[candidate.evaluation_index];
        const draft = result.baseline && season ? discoveryDraft(snapshot,candidate,team,counterparty) :
          "A completed comparison is needed to verify the discovery candidate.";
        return <details className="transaction-candidate" key={candidate.candidate_id}>
          <summary>{candidate.explicit_changes.map(move => player(move.player_id)).join(" / ")}
            {candidate.timeline.map(trade => ` / Week ${trade.scoring_week}`)}
            {result.baseline && season && <small>Requester rank {rank(result.baseline,team)} to {rank(season,team)} / Counterparty rank {rank(result.baseline,counterparty)} to {rank(season,counterparty)}</small>}
            {!season && <small>Unevaluated</small>}
          </summary>
          {candidate.limitation && <p>{candidate.limitation}</p>}
          {candidate.caveats.length > 0 && <ul>{candidate.caveats.map(text =>
            <li key={text}>{text.replaceAll("_", " ")}</li>)}</ul>}
          {onHandoff && (typeof draft==="string" ? <p>Editable evaluation unavailable. {draft}</p> :
            <button type="button" className="primary-button" onClick={event=>onHandoff(draft,event.currentTarget)}>Open in Evaluate</button>)}
          {(!onHandoff || typeof draft==="string") && result.baseline && season && <ProjectedTradeResult snapshot={snapshot} result={{
            ...candidate, scenario_id: candidate.candidate_id,
            baseline: result.baseline.season, hypothetical: season.season,
            baseline_final_roster: result.baseline.final_roster, hypothetical_final_roster: season.final_roster,
          }}/>}
        </details>;
      })}
    </>}
  </section>;
}
