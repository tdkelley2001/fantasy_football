import {useLayoutEffect, useRef} from "react";
import {commandTeamColor} from "./commandTeamIdentity";
import type {JourneyStandingsPoint, SnapshotSummary} from "./types/api";

export function SeasonJourney({snapshot, series, monteCarlo, focusBoundaryOnMobile, selected, onSelect}: {
  snapshot: SnapshotSummary;
  series?: readonly JourneyStandingsPoint[] | null;
  monteCarlo: boolean;
  focusBoundaryOnMobile?: boolean;
  selected: number | undefined;
  onSelect: (id: number) => void;
}) {
  return series?.length ? <JourneyChart {...{snapshot, series, monteCarlo, focusBoundaryOnMobile, selected, onSelect}}/>
    : <p>Weekly standings trajectories are unavailable.</p>;
}

function JourneyChart({snapshot, series, monteCarlo, focusBoundaryOnMobile, selected, onSelect}: {
  snapshot: SnapshotSummary;
  series: readonly JourneyStandingsPoint[];
  monteCarlo: boolean;
  focusBoundaryOnMobile?: boolean;
  selected: number | undefined;
  onSelect: (id: number) => void;
}) {
  const scroll = useRef<HTMLDivElement>(null);
  const teams = [...snapshot.teams].sort((a,b)=>a.team_id-b.team_id);
  const projected = series.filter(point=>point.basis==="projected");
  const start = series.find(point=>point.basis==="snapshot_start");
  const historical = series.some(point=>point.basis==="historical_replay");
  const hasReplayedRanks = series.some(point=>point.basis==="historical_replay" && point.status!=="unavailable");
  const first = series[0].scoring_week;
  const last = series[series.length-1].scoring_week;
  const steps = Math.max(1,last-first+Number(Boolean(start)));
  const width = Math.max(470, 78 + steps*40);
  const height = Math.max(280, 48+teams.length*19);
  const step = (width-56)/steps;
  const x = (point: JourneyStandingsPoint) =>
    28 + (point.scoring_week-first+Number(Boolean(start) && point.basis==="projected"))*step;
  const boundaryX = start && start.status!=="unavailable" && start.teams.some(row=>row.rank!=null) ? x(start) : null;
  useLayoutEffect(()=>{
    if (!focusBoundaryOnMobile || boundaryX===null || typeof window.matchMedia!=="function") return;
    const narrow = window.matchMedia("(max-width: 650px)");
    const showBoundary = () => {
      if (narrow.matches) scrollToJourneyPoint(scroll.current, width, boundaryX);
    };
    showBoundary();
    narrow.addEventListener("change", showBoundary);
    return ()=>narrow.removeEventListener("change", showBoundary);
  },[focusBoundaryOnMobile,boundaryX,width,snapshot.snapshot_id,snapshot.canonical_sha256]);
  const retrieval = new Date(snapshot.retrieval_finished_at_utc);
  const dateKnown = Number.isFinite(retrieval.getTime());
  const today = dateKnown && retrieval.toDateString()===new Date().toDateString();
  const boundaryLabel = today ? "Today" : "Snapshot";
  const y = (rank: number) => 24 + (rank-1)*(height-64)/Math.max(1,teams.length-1);
  const rankAt = (point: JourneyStandingsPoint, teamId: number) => {
    if (point.status==="unavailable") return undefined;
    const row=point.teams.find(item=>item.team_id===teamId);
    return row?.rank!=null && row.rank>=1 && row.rank<=teams.length ? row : undefined;
  };
  const slotCount = snapshot.league_structure?.championship_qualifier_count;
  const cutoff = slotCount!=null && slotCount>0 && slotCount<teams.length ? y(slotCount+.5):null;
  const rankedTeams = teams.map(team=>({team,color:commandTeamColor(team.team_id)}));
  const drawnTeams = [...rankedTeams].sort((a,b)=>Number(a.team.team_id===selected)-Number(b.team.team_id===selected));
  const hasGaps = series.some(point=>teams.some(team=>!rankAt(point,team.team_id)));
  const hasTies = series.some(point=>point.teams.some(row=>row.unresolved_tie));

  return <>
    <p className="journey-context">{monteCarlo
      ? "Deterministic reference for the Monte Carlo forecast"
      : hasReplayedRanks ? "Reconciled historical standings and deterministic weekly projections"
      : "Observed starting rank and projected weekly finishes"}</p>
    {start && <p className="journey-boundary-label"><strong>{boundaryLabel}</strong>
      {" · "}{dateKnown && <>{retrieval.toLocaleDateString(undefined,{year:"numeric",month:"short",day:"numeric"})}{" · "}</>}
      Entering Week {start.scoring_week}</p>}
    {hasReplayedRanks && <p className="journey-context">Dashed paths show reconciled historical ranks. Solid paths show projected ranks.</p>}
    {focusBoundaryOnMobile ? <div className="home-journey-navigation" role="group" aria-label="Journey week shortcuts">
      <button type="button" onClick={()=>{if(scroll.current)scroll.current.scrollLeft=0;}}>Week {first}</button>
      {boundaryX!==null && <button type="button" onClick={()=>scrollToJourneyPoint(scroll.current,width,boundaryX)}>Snapshot boundary</button>}
      {last!==first && <button type="button" onClick={()=>{if(scroll.current)scroll.current.scrollLeft=scroll.current.scrollWidth;}}>Week {last}</button>}
    </div> : <p className="journey-scroll-hint">Scroll the chart to see more weeks.</p>}
    <div className="journey-frame" style={{height}}>
      <svg className="journey-ranks" viewBox={`0 0 36 ${height}`} aria-hidden="true">
        <text x="4" y="12" className="journey-axis">Rank</text>
        {teams.map((_,index)=><text key={index} x="28" y={y(index+1)+3}
          textAnchor="end" className="journey-axis">{index+1}</text>)}
      </svg>
      <div ref={scroll} className="journey-scroll" role="region" aria-label="Weekly standings chart (scroll for more weeks)" tabIndex={0}>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{minWidth:historical?width:Math.min(680,width)}} aria-hidden="true">
        {teams.map((_,index)=><line key={index} x1="0" x2={width-14}
          y1={y(index+1)} y2={y(index+1)} className="journey-grid"/>)}
        {cutoff!==null && <g>
          <line x1="0" x2={width-14} y1={cutoff} y2={cutoff} className="journey-cutoff"/>
          <text x={width-18} y={cutoff-4} textAnchor="end" className="journey-cutoff-label">{slotCount}-team field reference</text>
        </g>}
        {start && <line x1={x(start)} x2={x(start)} y1="13" y2={height-28} className="journey-boundary"/>}
        {series.map(point=><text key={`${point.basis}:${point.scoring_week}`} x={x(point)} y={height-12}
          textAnchor="middle" className={`journey-axis ${point===start?"journey-boundary-tick":""}`}>{point===start ? boundaryLabel : `W${point.scoring_week}`}</text>)}
        {drawnTeams.map(({team,color})=>{
          const isFocused=team.team_id===selected;
          const lastRanked = isFocused ? [...series].reverse().find(point=>rankAt(point,team.team_id)) : undefined;
          const endpoint = lastRanked && rankAt(lastRanked,team.team_id)?.rank;
          const segments=series.slice(1).flatMap((point,index)=>{
            const before=series[index], from=rankAt(before,team.team_id), to=rankAt(point,team.team_id);
            const adjacent = before.basis==="snapshot_start" ? before.scoring_week===point.scoring_week :
              before.scoring_week+1===point.scoring_week;
            const verified = before.basis!=="historical_replay" || point.basis==="historical_replay" ||
              (point.basis==="snapshot_start" && point.historical_boundary==="reconciled");
            return from?.rank!=null && to?.rank!=null && adjacent && verified ? [{
              id:`${point.basis}:${point.scoring_week}`,
              observed:before.basis==="snapshot_start", historical:before.basis==="historical_replay",
              d:`M ${x(before)} ${y(from.rank)} L ${x(point)} ${y(to.rank)}`,
            }] : [];
          });
          return <g key={team.team_id} data-team-id={team.team_id}
            className={`journey-team ${isFocused?"focused":selected===undefined?"":"muted"}`} style={{color}}>
            {segments.map(segment=><g key={segment.id}>
              <path d={segment.d} className={`journey-line ${segment.observed?"from-observed":segment.historical?"historical":""}`}/>
              <path d={segment.d} className="journey-hit" onClick={()=>onSelect(team.team_id)}/>
            </g>)}
            {series.map(point=>{
              const row=rankAt(point,team.team_id);
              if (row?.rank==null) return null;
              return <circle key={`${point.basis}:${point.scoring_week}`} cx={x(point)} cy={y(row.rank)}
                r={isFocused?4:3} onClick={()=>onSelect(team.team_id)}
                className={`journey-point ${point.basis==="snapshot_start"?"observed":""} ${row.unresolved_tie?"tied":""}`}>
                <title>{`${team.display_name}, ${journeyPointLabel(point)}: rank ${row.rank}${row.unresolved_tie?", unresolved tie":""}`}</title>
              </circle>;
            })}
            {lastRanked && endpoint!=null && <text x={x(lastRanked)+(x(lastRanked)<110?8:-8)} y={y(endpoint)-7}
              textAnchor={x(lastRanked)<110?"start":"end"} className="journey-endpoint" onClick={()=>onSelect(team.team_id)}>{team.display_name}</text>}
          </g>;
        })}
      </svg>
      </div>
    </div>
    <p className="journey-context">{!hasReplayedRanks && "Historical weekly ranks are unavailable."}
      {!projected.length && " Projected regular-season weeks are unavailable."}
      {start?.historical_boundary==="records_unverified" && " A complete settled prefix could not be reconciled to the snapshot standings."}
      {start?.historical_boundary==="ranks_unverified" && " The last replayed ranks do not establish the same ordering as the snapshot. The paths stay separate."}
      {hasTies && " Ringed weekly points show shared ranks with unresolved tiebreakers."}
      {hasGaps && " Gaps indicate unavailable ranks."}
    </p>
    <ul className="journey-legend" aria-label="Select a journey team">
      {rankedTeams.map(({team,color})=><li key={team.team_id}>
        <button type="button" aria-pressed={selected===team.team_id} onClick={()=>onSelect(team.team_id)}>
          <span className="journey-swatch" style={{background:color}} aria-hidden="true"/>{team.display_name}
        </button>
      </li>)}
    </ul>
  </>;
}

function scrollToJourneyPoint(scroll: HTMLDivElement | null, width: number, x: number) {
  const drawing = scroll?.querySelector("svg");
  if (scroll && drawing) {
    const scale = drawing.getBoundingClientRect().width / width;
    scroll.scrollLeft = Math.max(0, x * scale - scroll.clientWidth * 0.42);
  }
}

function journeyPointLabel(point: JourneyStandingsPoint) {
  if (point.basis==="snapshot_start") return `Snapshot entering Week ${point.scoring_week}`;
  const week = `Week ${point.scoring_week}`;
  if (point.basis==="projected") return `${week} / Projected`;
  if (point.period_end_scoring_week!=null && point.scoring_week<point.period_end_scoring_week) {
    return `${week} / Period ends Week ${point.period_end_scoring_week}`;
  }
  return `${week} / Historical replay`;
}

export function JourneyTeamWeeks({series, teamId}: {
  series: readonly JourneyStandingsPoint[];
  teamId: number;
}) {
  return <details className="journey-weekly">
    <summary>Weekly standings</summary>
    <ul>{series.map(point=>{
      const row=point.status==="unavailable" ? undefined : point.teams.find(item=>item.team_id===teamId);
      return <li key={`${point.basis}:${point.scoring_week}`}>
        {journeyPointLabel(point)}
        <b>{row?.rank==null ? "Unavailable" : `Rank ${row.rank}${row.unresolved_tie?" (unresolved tie)":""}`}</b>
      </li>;
    })}</ul>
  </details>;
}
