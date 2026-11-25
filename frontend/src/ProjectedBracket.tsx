import {useLayoutEffect, useRef, useState} from "react";
import {commandTeamColor} from "./commandTeamIdentity";
import type {ProjectedBaselineResult, ProjectedChampionshipRound, ProjectedPostseasonMatchup, SnapshotSummary} from "./types/api";

type Props = {
  snapshot: SnapshotSummary;
  result: ProjectedBaselineResult | null;
  selected: number | undefined;
  onSelect: (id: number) => void;
};

type Advancement = {from: string; to: string; outcome: "winner" | "loser"; focused: boolean};

function BracketLinks({edges}: {edges: readonly Advancement[]}) {
  const drawing = useRef<SVGSVGElement>(null);
  const [paths,setPaths] = useState<readonly string[]>([]);

  useLayoutEffect(()=>{
    const frame = drawing.current?.parentElement;
    if (!frame) return;
    const slots = new Map(Array.from(frame.querySelectorAll<HTMLElement>("[data-bracket-node]"),
      slot=>[slot.dataset.bracketNode,slot]));
    const update=()=>{
      const bounds=frame.getBoundingClientRect();
      setPaths(edges.map(({from,to,outcome})=>{
        const start=slots.get(from)?.getBoundingClientRect();
        const end=slots.get(to)?.getBoundingClientRect();
        if(!start || !end || start.right>=end.left)return "";
        const offset=outcome==="loser"?5:0;
        const x1=start.right-bounds.left, x2=end.left-bounds.left, mid=(x1+x2)/2+offset;
        const y1=start.top+start.height/2-bounds.top+offset, y2=end.top+end.height/2-bounds.top+offset;
        return `M ${x1} ${y1} H ${mid} V ${y2} H ${x2}`;
      }));
    };
    update();
    if (typeof ResizeObserver==="undefined") return;
    const observer=new ResizeObserver(update);
    observer.observe(frame);
    slots.forEach(slot=>observer.observe(slot));
    return ()=>observer.disconnect();
  },[edges]);

  return <svg ref={drawing} className="bracket-links" aria-hidden="true">
    {edges.map(({from,to,outcome,focused},i)=><path key={`${from}:${to}:${outcome}`}
      data-from={from} data-to={to} data-outcome={outcome} d={paths[i]??""} className={focused?"focused":undefined}/>)}
  </svg>;
}

export function ProjectedBracket({snapshot, result, selected, onSelect}: Props) {
  if (!result) return <p>Projected postseason matchups are unavailable.</p>;
  const championship = result.postseason.filter(match=>match.bracket_type==="championship");
  const consolation = result.postseason.filter(match=>match.bracket_type==="consolation");
  const placements = result.postseason.filter(match=>match.bracket_type==="placement");
  return <>
    <BracketRounds {...{snapshot,result,selected,onSelect}} matches={championship}
      configured={result.championship_rounds} kind="Championship"/>
    {(consolation.length>0 || Boolean(result.consolation_rounds?.length)) &&
      <section className="consolation-bracket" aria-label="Projected consolation bracket">
        <BracketRounds {...{snapshot,result,selected,onSelect}} matches={consolation}
          configured={result.consolation_rounds} kind="Consolation"/>
      </section>}
    {placements.length>0 && <details className="bracket-secondary">
      <summary>Projected championship placement matchups</summary>
      <BracketRounds {...{snapshot,result,selected,onSelect}} matches={placements} kind="Placement"/>
    </details>}
  </>;
}

type BracketProps = Omit<Props,"result"> & {
  result: ProjectedBaselineResult;
  matches: readonly ProjectedPostseasonMatchup[];
  configured?: readonly ProjectedChampionshipRound[] | null;
  kind: "Championship" | "Consolation" | "Placement";
};

function BracketRounds({snapshot,result,selected,onSelect,matches,configured,kind}:BracketProps) {
  const consolation = kind==="Consolation";
  const rounds = configured ??
    [...new Set(matches.map(match=>match.round_number))].sort((a,b)=>a-b).map(number=>({
      round_number:number, scoring_weeks:matches.find(match=>match.round_number===number)?.scoring_weeks??[], nodes:[],
    }));
  const teams=new Map(snapshot.teams.map(team=>[team.team_id,team.display_name]));
  const seededTeams=new Map(result.teams.filter(team=>consolation
    ?team.championship_qualifier===false:team.championship_qualifier===true)
    .map(team=>[team.team_id,team.postseason_seed]));
  const finalPlaces=new Map(result.teams.map(team=>[team.team_id,team.final_placement]));
  const nodes=new Map(rounds.flatMap(round=>round.nodes.map(node=>[node.node_id,{round:round.round_number,position:node.position+1}] as const)));

  const matchByNode = new Map(matches.filter(match=>match.purpose!==undefined).map(match=>[match.purpose,match]));
  const edges = rounds.flatMap(round=>round.nodes.flatMap(node=>node.sources.flatMap<Advancement>(source=>{
    const prior=source.matchup_id===null?undefined:nodes.get(source.matchup_id);
    const outcome=source.outcome;
    if(!source.matchup_id || !prior || prior.round>=round.round_number ||
      (outcome!=="winner" && outcome!=="loser"))return [];
    const origin=matchByNode.get(source.matchup_id), target=matchByNode.get(node.node_id);
    const routedTeam=outcome==="loser"?origin?.loser_team_id:origin?.winner_team_id;
    return [{from:source.matchup_id,to:node.node_id,outcome,
      focused:selected!==undefined && routedTeam===selected &&
        (target?.home_team_id===selected || target?.away_team_id===selected)}];
  })));

  const teamButton = (id: number | null, match: ProjectedPostseasonMatchup, total: number | null) => {
    const name=id===null?undefined:teams.get(id);
    if (id===null || name===undefined) return <span className="bracket-pending">Participant unresolved</span>;
    const seed=seededTeams.get(id);
    const place=consolation && match.round_number===rounds.at(-1)?.round_number ? finalPlaces.get(id):null;
    const winner=match.winner_team_id===id && match.status!=="bye";
    const eliminated=match.status==="complete" && match.winner_team_id!==null && match.winner_team_id!==id;
    return <button type="button" className="bracket-team" data-winner={winner || undefined} style={{"--postseason-accent":commandTeamColor(id)} as React.CSSProperties} aria-pressed={selected===id} onClick={()=>onSelect(id)}>
      <span>{seed!=null && <small>Seed {seed}</small>}<strong><span className="journey-swatch" style={{background:commandTeamColor(id)}} aria-hidden="true"/> {name}</strong></span>
      <span>{total!=null && <b>{total.toFixed(2)}</b>}{winner && <small>Winner</small>}{eliminated && <small>Loss</small>}{place!=null && <small>Place {place}</small>}</span>
    </button>;
  };

  const contest = (match: ProjectedPostseasonMatchup) => <>
    {teamButton(match.home_team_id,match,match.home_total)}
    {match.status==="bye" ? <p className="bracket-status">{consolation ? "Bye" : "Bye / Advances"}</p> :
      teamButton(match.away_team_id,match,match.away_total)}
    {match.status!=="bye" && match.winner_team_id===null && <p className="bracket-status">
      {match.status==="in_progress" ? "Round incomplete" : "Outcome unresolved"}
    </p>}
    {(match.scoring_weeks?.length??0)>1 && Boolean(match.weekly_scores?.length) &&
      <details className="bracket-weekly"><summary>Weekly scoring</summary>
        <ul>{match.weekly_scores?.map(score=><li key={`${score.scoring_week}:${score.team_id}`}>
          Week {score.scoring_week} / {teams.get(score.team_id)??"Team unavailable"} / {score.points.toFixed(2)}
        </li>)}</ul>
      </details>}
  </>;

  return <>
    <p className="bracket-context">Projected {kind.toLowerCase()} bracket</p>
    {consolation && edges.some(edge=>edge.outcome==="loser") &&
      <p className="bracket-context bracket-route-key">Solid paths show winner routing. Dashed paths show loser routing.</p>}
    {rounds.length===0 ? <p>Projected {kind.toLowerCase()} rounds are unavailable.</p> :
      <div className="bracket-scroll" role="region" aria-label={`${kind} rounds`} tabIndex={0}>
      <div className="bracket-rounds" style={selected===undefined?undefined:{"--postseason-accent":commandTeamColor(selected)} as React.CSSProperties}>
        {edges.length>0 && <BracketLinks edges={edges}/>}
        {rounds.map((round,index)=>{
          const roundMatches=matches.filter(match=>match.round_number===round.round_number);
          const title=kind==="Championship" && index===rounds.length-1 && configured?.length
            ? `Championship / Round ${round.round_number}` : `Round ${round.round_number}`;
          return <section key={round.round_number} className="bracket-round" aria-label={kind==="Championship"?title:`${kind} round ${round.round_number}`}>
            <h4>{title}</h4>
            <p className="bracket-context">{round.scoring_weeks.length
              ? `${round.scoring_weeks.length===1?"Week":"Weeks"} ${round.scoring_weeks.join(", ")}`
              : "Scoring weeks unavailable"}</p>
            {!round.nodes.length && !roundMatches.length && <p>Matchups unresolved</p>}
            {consolation && !round.nodes.length && !roundMatches.length && round.round_number>1 &&
              <p className="bracket-status">Routing unresolved</p>}
            <ul>
              {round.nodes.map(node=>{
                const match=roundMatches.find(item=>item.purpose===node.node_id);
                return <li key={node.node_id} className="bracket-slot" data-bracket-node={node.node_id}>
                  <small>Match {node.position+1}</small>
                  {match ? contest(match) : <p className="bracket-pending">Participants unresolved</p>}
                  {(!match || node.sources.some(source=>source.matchup_id!==null)) && <ul className="bracket-sources" aria-label="Bracket sources">
                    {node.sources.map(({seed,matchup_id,outcome},i)=>{
                      const prior=matchup_id===null?undefined:nodes.get(matchup_id);
                      const label=outcome==="loser"?"Loser":
                        consolation && matchByNode.get(matchup_id??undefined)?.status==="bye"?"Bye team":"Winner";
                      return <li key={i}>{seed!==null ? `Seed ${seed}` : prior && prior.round<round.round_number && (outcome==="winner" || outcome==="loser")
                        ? `${label} of round ${prior.round}, match ${prior.position}` : "Source unresolved"}</li>;
                    })}
                  </ul>}
                </li>;
              })}
              {roundMatches.filter(match=>!round.nodes.some(node=>node.node_id===match.purpose)).map(match=>
                <li key={match.matchup_id} className="bracket-slot">
                  {kind==="Placement" && <small>Placement game</small>}
                  {contest(match)}
                  {consolation && (round.round_number>1 || !configured) &&
                    <p className="bracket-status">Routing unresolved</p>}
                </li>)}
            </ul>
          </section>;
        })}
      </div>
      </div>}
  </>;
}
