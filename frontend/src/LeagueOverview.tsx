import { useMemo, useState } from "react";
import { ArrowRight, CalendarDays, Database, ShieldCheck, Trophy } from "lucide-react";
import type { SnapshotSummary, TeamSummary } from "./types/api";

export function LeagueOverview({snapshot}:{snapshot:SnapshotSummary}) {
  const teams=useMemo(()=>[...snapshot.teams].sort((a,b)=>(a.standing??999)-(b.standing??999)||a.team_id-b.team_id),[snapshot]);
  const [selectedId,setSelectedId]=useState(teams[0]?.team_id);
  const selected=teams.find(team=>team.team_id===selectedId);
  const teamById=useMemo(()=>new Map(teams.map(team=>[team.team_id,team])),[teams]);
  const period=snapshot.matchup_periods.find(item=>item.scoring_weeks.includes(snapshot.first_simulation_week))??snapshot.matchup_periods[0];
  const matchups=snapshot.matchups.filter(item=>item.matchup_period_id===period?.matchup_period_id);
  const selectedGame=matchups.find(game=>game.home_team_id===selectedId||game.away_team_id===selectedId)??matchups[0];
  const home=teamById.get(selectedGame?.home_team_id??-1);
  const away=teamById.get(selectedGame?.away_team_id??-1);
  const maxPoints=Math.max(...teams.map(team=>team.points_for),1);
  const qualifierCount=snapshot.league_structure?.championship_qualifier_count;
  return <div className="overview">
    <header className="overview-masthead">
      <div><span className="overline">League overview · observed snapshot</span><h1>{snapshot.league_name??`League ${snapshot.league_id}`}</h1><p>{snapshot.season} season <i/> {teams.length} teams <i/> simulation horizon weeks {snapshot.first_simulation_week}–{snapshot.final_simulation_week}</p></div>
      <div className="snapshot-stamp"><Database/><span><strong>Canonical snapshot</strong>{formatDate(snapshot.published_at_utc)}</span></div>
    </header>

    <div className="overview-lead">
      <section className="points-story" aria-labelledby="points-title">
        <SectionHeading eyebrow="Competitive profile" title="League points landscape" id="points-title" note="Observed points for · not a forecast"/>
        <div className="points-chart" aria-label="Horizontal comparison of observed points for by team">{teams.map(team=><button key={team.team_id} className={selectedId===team.team_id?"selected":""} onClick={()=>setSelectedId(team.team_id)} aria-label={`${team.display_name}, ${team.points_for.toFixed(1)} observed points for`}><span className="chart-rank">{team.standing??"—"}</span><strong>{team.display_name}</strong><span className="bar-track"><span style={{width:`${team.points_for/maxPoints*100}%`}}/></span><b>{team.points_for.toFixed(1)}</b></button>)}</div>
        <div className="chart-axis"><span>0</span><span>{(maxPoints/2).toFixed(0)}</span><span>{maxPoints.toFixed(0)} points</span></div>
      </section>

      <aside className="team-focus" aria-label="Selected team detail" aria-live="polite">
        <span className="overline">Team focus</span><div className="team-identity"><Monogram name={selected?.display_name??"TBD"}/><div><h2>{selected?.display_name??"Select a team"}</h2><p>Official standing {selected?.standing??"unresolved"}</p></div></div>
        {selected&&<><div className="focus-numbers"><DataPoint label="Record" value={`${selected.wins}–${selected.losses}${selected.ties?`–${selected.ties}`:""}`}/><DataPoint label="Points for" value={selected.points_for.toFixed(1)}/><DataPoint label="Playoff seed" value={String(selected.playoff_seed??"Unresolved")}/><DataPoint label="Waiver priority" value={String(selected.waiver_priority??"Unresolved")}/></div><p className="integrity-note"><ShieldCheck/> Values are current snapshot facts, not simulated outcomes.</p></>}
      </aside>
    </div>

    <section className="matchup-feature" aria-labelledby="matchup-title">
      <div className="matchup-copy"><span className="overline">Featured schedule context</span><h2 id="matchup-title">{period?`Matchup period ${period.matchup_period_id}`:"Schedule unresolved"}</h2><p>{period?`Scoring week${period.scoring_weeks.length===1?"":"s"} ${period.scoring_weeks.join(", ")} · ${label(period.phase)}`:"No applicable period record"}</p></div>
      {selectedGame?<div className="matchup-presentation"><TeamBadge team={away}/><div className="matchup-center"><span>{selectedGame.entry_status}</span><strong>VS</strong><small>{selectedGame.bracket_type??"League schedule"}</small></div><TeamBadge team={home}/></div>:<p className="empty-inline">No matchup record is available for this period.</p>}
      <div className="matchup-index"><CalendarDays/><strong>{matchups.length}</strong><span>scheduled matchup records</span></div>
    </section>

    <div className="overview-lower">
      <section className="standings-detail" tabIndex={-1} aria-labelledby="standings-title">
        <SectionHeading eyebrow="Official order" title="Compact standings" id="standings-title" note="Source-backed"/>
        <div className="standings-list" aria-label="League standings"><div className="standings-head"><span>Pos</span><span>Club</span><span>Record</span><span>PF</span><span>Postseason</span></div>{teams.map(team=><button key={team.team_id} onClick={()=>setSelectedId(team.team_id)} className={selectedId===team.team_id?"selected":""}><span>{team.standing??"—"}</span><span><Monogram name={team.display_name}/><strong>{team.display_name}</strong></span><span>{team.wins}–{team.losses}</span><span>{team.points_for.toFixed(1)}</span><span>{team.playoff_seed?`Seed ${team.playoff_seed}`:"Unresolved"}</span></button>)}</div>
      </section>
      <aside className="postseason-context" aria-label="Configured postseason context"><span className="overline">Configured postseason</span><Trophy/><h2>{qualifierCount??"Unresolved"}</h2><p>championship qualifiers</p><div className="qualification-scale" aria-label={qualifierCount===null||qualifierCount===undefined?"Qualifier count unresolved":`${qualifierCount} of ${teams.length} teams qualify`}>{teams.map((team,index)=><span key={team.team_id} className={qualifierCount!==null&&qualifierCount!==undefined&&index<qualifierCount?"in":""} title={team.display_name}/>)}</div><dl><div><dt>Rounds</dt><dd>{snapshot.league_structure?.championship_round_count??"—"}</dd></div><div><dt>Consolation</dt><dd>{formatEnabled(snapshot.league_structure?.consolation_enabled)}</dd></div><div><dt>Roster capacity</dt><dd>{snapshot.league_structure?.ordinary_roster_capacity??"—"}</dd></div></dl><small>Configuration context only. Qualification probabilities are deferred.</small></aside>
    </div>

    <footer className="overview-provenance"><div><Database/><span><strong>{snapshot.source_count} linked evidence sources</strong><small>Retrieved {formatDate(snapshot.retrieval_finished_at_utc)}</small></span></div><div>{snapshot.players.length} player records · {snapshot.roster_assignments.length} roster assignments · {snapshot.capabilities.length} capability records</div><button onClick={()=>document.querySelector<HTMLElement>(".standings-detail")?.focus()}>Inspect league detail <ArrowRight/></button></footer>
  </div>;
}

function SectionHeading({eyebrow,title,id,note}:{eyebrow:string;title:string;id:string;note:string}) { return <header className="section-heading"><div><span className="overline">{eyebrow}</span><h2 id={id}>{title}</h2></div><small>{note}</small></header>; }
function Monogram({name}:{name:string}) { return <span className="monogram" aria-hidden="true">{name.split(/\s+/).map(part=>part[0]).join("").slice(0,3).toUpperCase()}</span>; }
function DataPoint({label:caption,value}:{label:string;value:string}) { return <div><span>{caption}</span><strong>{value}</strong></div>; }
function TeamBadge({team}:{team:TeamSummary|undefined}) { return <div className="team-badge"><Monogram name={team?.display_name??"TBD"}/><span><strong>{team?.display_name??"TBD"}</strong><small>{team?`${team.wins}–${team.losses} · ${team.points_for.toFixed(1)} PF`:"Team unresolved"}</small></span></div>; }
function label(value:string) { return value.replaceAll("_"," ").replace(/\b\w/g,letter=>letter.toUpperCase()); }
function formatEnabled(value:boolean|null|undefined) { return value===true?"Enabled":value===false?"Disabled":"Unresolved"; }
function formatDate(value:string) { return new Intl.DateTimeFormat(undefined,{dateStyle:"medium",timeStyle:"short"}).format(new Date(value)); }
