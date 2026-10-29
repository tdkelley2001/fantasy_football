import { useMemo, useState } from "react";
import { ChevronRight, Crosshair, Layers3, Map as MapIcon, Radio, Swords } from "lucide-react";
import type { SnapshotSummary, TeamSummary } from "./types/api";

export type VisualConcept = "shell" | "tactical" | "landscape" | "table";
const concepts: readonly [VisualConcept,string,string][] = [
  ["shell","Current shell","Comparison"], ["tactical","A · Tactical map","Ordinal league map"],
  ["landscape","B · Competitive landscape","Competition structure"], ["table","C · Strategy table","Field workspace"],
];

function Switcher({concept,onChange}:{concept:VisualConcept;onChange:(value:VisualConcept)=>void}) {
  return <div className="concept-bar" aria-label="Visual direction prototypes"><div><span>Design exploration</span><strong>Living League concepts</strong></div><div role="tablist" aria-label="Choose visual concept">{concepts.map(([id,label,description])=><button key={id} role="tab" aria-selected={concept===id} onClick={()=>onChange(id)}><strong>{label}</strong><span>{description}</span></button>)}</div></div>;
}

function Render({concept,snapshot}:{concept:Exclude<VisualConcept,"shell">;snapshot:SnapshotSummary}) {
  if(concept==="tactical") return <TacticalMap snapshot={snapshot}/>;
  if(concept==="landscape") return <CompetitiveLandscape snapshot={snapshot}/>;
  return <StrategyTable snapshot={snapshot}/>;
}
export const ConceptSwitcher=Object.assign(Switcher,{Render});

function useLeague(snapshot:SnapshotSummary) {
  const teams=useMemo(()=>[...snapshot.teams].sort((a,b)=>(a.standing??999)-(b.standing??999)||a.team_id-b.team_id),[snapshot]);
  const teamById=useMemo(()=>new Map(teams.map(team=>[team.team_id,team])),[teams]);
  const period=snapshot.matchup_periods.find(item=>item.scoring_weeks.includes(snapshot.first_simulation_week))??snapshot.matchup_periods[0];
  const matchups=snapshot.matchups.filter(item=>item.matchup_period_id===period?.matchup_period_id);
  return {teams,teamById,period,matchups};
}
function useSelection(teams:readonly TeamSummary[]) { const [id,setId]=useState<number|undefined>(teams[0]?.team_id); return {selected:teams.find(team=>team.team_id===id),setId}; }

function TacticalMap({snapshot}:{snapshot:SnapshotSummary}) {
  const {teams,matchups,teamById}=useLeague(snapshot); const {selected,setId}=useSelection(teams);
  const selectedMatchups=matchups.filter(game=>game.home_team_id===selected?.team_id||game.away_team_id===selected?.team_id);
  return <section className="prototype prototype-map" aria-label="Tactical League Map prototype">
    <PrototypeTitle icon={<MapIcon/>} code="Concept A" title="Tactical League Map" copy="Official standing order rendered as a navigable league constellation. Position is ordinal and does not encode probability or team strength."/>
    <div className="map-stage"><div className="map-axis"><span>Standing 1</span><span>Official standing order</span><span>Standing {teams.length}</span></div><div className="map-track" aria-label="Teams ordered by official standing">{teams.map((team,index)=><button key={team.team_id} className={selected?.team_id===team.team_id?"selected":""} style={{"--rank":index} as React.CSSProperties} onClick={()=>setId(team.team_id)} aria-pressed={selected?.team_id===team.team_id}><span>{team.standing??"—"}</span><strong>{initials(team.display_name)}</strong><small>{team.wins}–{team.losses}</small></button>)}</div>
      <aside className="map-intel" aria-live="polite"><span className="prototype-kicker">Selected club</span><h2>{selected?.display_name??"Select a team"}</h2>{selected&&<><div className="fact-strip"><Fact label="Record" value={`${selected.wins}–${selected.losses}`}/><Fact label="Points" value={selected.points_for.toFixed(1)}/><Fact label="Seed" value={String(selected.playoff_seed??"Unresolved")}/></div><h3>Current matchup link</h3>{selectedMatchups.length?selectedMatchups.map(game=>{const other=teamById.get(game.home_team_id===selected.team_id?game.away_team_id!:game.home_team_id!);return <p key={game.matchup_id} className="linked-opponent"><Radio/> {other?.display_name??"Opponent TBD"}</p>}):<p className="quiet">No current matchup record.</p>}</>}</aside>
    </div>
  </section>;
}

function CompetitiveLandscape({snapshot}:{snapshot:SnapshotSummary}) {
  const {teams,matchups,teamById,period}=useLeague(snapshot); const {selected,setId}=useSelection(teams);
  const qualifierCount=snapshot.league_structure?.championship_qualifier_count;
  const qualifiers=qualifierCount===null||qualifierCount===undefined?[]:teams.slice(0,qualifierCount); const outside=qualifierCount===null||qualifierCount===undefined?teams:teams.slice(qualifierCount);
  return <section className="prototype prototype-landscape" aria-label="Competitive Landscape prototype">
    <PrototypeTitle icon={<Layers3/>} code="Concept B" title="Competitive Landscape" copy="The configured championship field, official standings, and scheduled matchup relationships form one competition view—without invented odds or tiers."/>
    <div className="landscape-grid"><div className="field-column"><header><span>Configured championship field</span><strong>{qualifierCount??"Unresolved"} places</strong></header>{qualifiers.length?qualifiers.map(team=><LandscapeTeam key={team.team_id} team={team} selected={selected?.team_id===team.team_id} onClick={()=>setId(team.team_id)}/>):<p className="quiet">Qualification structure is unresolved.</p>}</div>
      <div className="matchup-spine"><span className="prototype-kicker">Matchup period {period?.matchup_period_id??"unresolved"}</span>{matchups.map(game=><div className="versus-node" key={game.matchup_id}><button onClick={()=>game.away_team_id&&setId(game.away_team_id)}>{teamById.get(game.away_team_id??-1)?.display_name??"TBD"}</button><Swords/><button onClick={()=>game.home_team_id&&setId(game.home_team_id)}>{teamById.get(game.home_team_id??-1)?.display_name??"TBD"}</button></div>)}</div>
      <div className="field-column outside"><header><span>Outside configured field</span><strong>{outside.length} clubs</strong></header>{outside.map(team=><LandscapeTeam key={team.team_id} team={team} selected={selected?.team_id===team.team_id} onClick={()=>setId(team.team_id)}/>)}</div></div>
    {selected&&<div className="landscape-focus"><span>Focused team</span><strong>{selected.display_name}</strong><p>Standing {selected.standing??"unresolved"} · {selected.wins}–{selected.losses} · {selected.points_for.toFixed(1)} source points</p></div>}
  </section>;
}

function StrategyTable({snapshot}:{snapshot:SnapshotSummary}) {
  const {teams,matchups,teamById,period}=useLeague(snapshot); const {selected,setId}=useSelection(teams);
  return <section className="prototype prototype-table" aria-label="Digital Strategy Table prototype">
    <PrototypeTitle icon={<Crosshair/>} code="Concept C" title="Digital Strategy Table" copy="The field is the primary workspace. Scheduled matchup objects occupy lanes; selecting a club summons factual intelligence at the table edge."/>
    <div className="strategy-field"><div className="field-numbers" aria-hidden="true"><span>10</span><span>20</span><span>30</span><span>40</span><span>50</span><span>40</span><span>30</span><span>20</span><span>10</span></div><div className="field-matchups">{matchups.map((game,index)=><div className="field-matchup" key={game.matchup_id} style={{"--lane":index} as React.CSSProperties}><button className={selected?.team_id===game.away_team_id?"selected":""} onClick={()=>game.away_team_id&&setId(game.away_team_id)}>{initials(teamById.get(game.away_team_id??-1)?.display_name??"TBD")}</button><span>VS</span><button className={selected?.team_id===game.home_team_id?"selected":""} onClick={()=>game.home_team_id&&setId(game.home_team_id)}>{initials(teamById.get(game.home_team_id??-1)?.display_name??"TBD")}</button></div>)}</div><div className="table-legend">Scheduled matchups · period {period?.matchup_period_id??"unresolved"}</div>
      <aside className="table-intel" aria-live="polite"><span className="prototype-kicker">Table intelligence</span><h2>{selected?.display_name??"Select a club"}</h2>{selected&&<><p>Official standing <strong>{selected.standing??"—"}</strong></p><p>Record <strong>{selected.wins}–{selected.losses}</strong></p><p>Points for <strong>{selected.points_for.toFixed(1)}</strong></p><button>Open context <ChevronRight/></button><small>Exploration only · no analytical action is executed</small></>}</aside>
    </div>
  </section>;
}

function PrototypeTitle({icon,code,title,copy}:{icon:React.ReactNode;code:string;title:string;copy:string}) { return <header className="prototype-title">{icon}<div><span className="prototype-kicker">{code} · visual review prototype</span><h1 id={`${title.toLowerCase().replaceAll(" ","-")}-title`}>{title}</h1><p>{copy}</p></div><em>Sanitized fixture compatible</em></header>; }
function LandscapeTeam({team,selected,onClick}:{team:TeamSummary;selected:boolean;onClick:()=>void}) { return <button className={`landscape-team ${selected?"selected":""}`} onClick={onClick} aria-pressed={selected}><span>{team.standing??"—"}</span><div><strong>{team.display_name}</strong><small>{team.wins}–{team.losses} · {team.points_for.toFixed(1)} pts</small></div><ChevronRight/></button>; }
function Fact({label,value}:{label:string;value:string}) { return <div><span>{label}</span><strong>{value}</strong></div>; }
function initials(name:string) { return name.split(/\s+/).map(part=>part[0]).join("").slice(0,3).toUpperCase(); }
