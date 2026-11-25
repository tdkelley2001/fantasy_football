import {commandTeamColor} from "./commandTeamIdentity";
import type {ProjectedBaselineResult, ProjectedPostseasonMatchup, SnapshotSummary} from "./types/api";

type Props = {
  snapshot: SnapshotSummary;
  result: ProjectedBaselineResult | null;
  selected: number | undefined;
  onSelect: (id: number) => void;
};

export function ProjectedBracket({snapshot, result, selected, onSelect}: Props) {
  if (!result) return <p>Projected postseason matchups are unavailable.</p>;
  const championship = result.postseason.filter(match=>match.bracket_type==="championship");
  const otherMatches = result.postseason.filter(match=>match.bracket_type!=="championship");
  const rounds = result.championship_rounds ??
    [...new Set(championship.map(match=>match.round_number))].sort((a,b)=>a-b).map(number=>({
      round_number:number, matchup_period_id:championship.find(match=>match.round_number===number)?.matchup_period_id,
      scoring_weeks:championship.find(match=>match.round_number===number)?.scoring_weeks??[], nodes:[],
    }));
  const teams=new Map(snapshot.teams.map(team=>[team.team_id,team.display_name]));
  const seeds=new Map(result.teams.filter(team=>team.championship_qualifier===true)
    .map(team=>[team.team_id,team.postseason_seed]));
  const nodes=new Map(rounds.flatMap(round=>round.nodes.map(node=>[node.node_id,{round:round.round_number,position:node.position+1}] as const)));

  const teamButton = (id: number | null, match: ProjectedPostseasonMatchup, total: number | null) => {
    const name=id===null?undefined:teams.get(id);
    if (id===null || name===undefined) return <span className="bracket-pending">Participant unresolved</span>;
    const seed=seeds.get(id);
    const winner=match.winner_team_id===id && match.status!=="bye";
    return <button type="button" className="bracket-team" aria-pressed={selected===id} onClick={()=>onSelect(id)}>
      <span>{seed!=null && <small>Seed {seed}</small>}<strong><span className="journey-swatch" style={{background:commandTeamColor(id)}} aria-hidden="true"/> {name}</strong></span>
      <span>{total!=null && <b>{total.toFixed(2)}</b>}{winner && <small>Winner</small>}</span>
    </button>;
  };

  const contest = (match: ProjectedPostseasonMatchup) => <>
    {teamButton(match.home_team_id,match,match.home_total)}
    {match.status==="bye" ? <p className="bracket-status">Bye / Advances</p> :
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
    <p className="bracket-context">Projected championship bracket</p>
    {rounds.length===0 ? <p>Projected championship rounds are unavailable.</p> :
      <div className="bracket-rounds" role="group" aria-label="Championship rounds">
        {rounds.map((round,index)=>{
          const matches=championship.filter(match=>match.round_number===round.round_number);
          const title=index===rounds.length-1 && result.championship_rounds?.length
            ? `Championship / Round ${round.round_number}` : `Round ${round.round_number}`;
          return <section key={round.round_number} className="bracket-round" aria-label={title}>
            <h4>{title}</h4>
            <p className="bracket-context">{round.scoring_weeks.length
              ? `${round.scoring_weeks.length===1?"Week":"Weeks"} ${round.scoring_weeks.join(", ")}`
              : "Scoring weeks unavailable"}</p>
            {!round.nodes.length && !matches.length && <p>Matchups unresolved</p>}
            <ul>
              {round.nodes.map(node=>{
                const match=matches.find(item=>item.purpose===node.node_id);
                return <li key={node.node_id} className="bracket-slot">
                  <small>Match {node.position+1}</small>
                  {match ? contest(match) : <p className="bracket-pending">Participants unresolved</p>}
                  {(!match || node.sources.some(source=>source.matchup_id!==null)) && <ul className="bracket-sources" aria-label="Bracket sources">
                    {node.sources.map(({seed,matchup_id,outcome},i)=>{
                      const prior=matchup_id===null?undefined:nodes.get(matchup_id);
                      return <li key={i}>{seed!==null ? `Seed ${seed}` : prior && outcome==="winner"
                        ? `Winner of round ${prior.round}, match ${prior.position}` : "Source unresolved"}</li>;
                    })}
                  </ul>}
                </li>;
              })}
              {matches.filter(match=>!round.nodes.some(node=>node.node_id===match.purpose)).map(match=>
                <li key={match.matchup_id} className="bracket-slot">{contest(match)}</li>)}
            </ul>
          </section>;
        })}
      </div>}
    {otherMatches.length>0 && <details className="bracket-secondary"><summary>Projected consolation and placement matchups</summary>
      <ul>{otherMatches.map(match=><li key={match.matchup_id} className="bracket-slot">
        <small>{match.bracket_type} / Round {match.round_number}{match.scoring_weeks?.length ? ` / Weeks ${match.scoring_weeks.join(", ")}` : ""}</small>
        {contest(match)}
      </li>)}</ul>
    </details>}
  </>;
}
