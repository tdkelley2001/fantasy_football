import React, {useState} from 'react';
import {weeklyTrend, standingsDetail} from './season-view.mjs';

const points = value => value == null ? '—' : value.toLocaleString(undefined, {maximumFractionDigits:1, minimumFractionDigits:1});

function SummaryCard({label, value, note}) {
  return <article className="seasonmetric"><span>{label}</span><strong>{value}</strong><p>{note}</p></article>;
}

function ScoringTrend({rows, name}) {
  if (!rows.length) return <p className="empty">No projected scoring weeks remain.</p>;
  const values = rows.flatMap(r => [r.points, r.average]).filter(v => v != null);
  const low = Math.min(0, ...values), high = Math.max(1, ...values), span = high - low;
  const x = i => 42 + i * 520 / Math.max(1, rows.length - 1);
  const y = value => 182 - (value-low)/span*145;
  const path = key => rows.map((r,i) => r[key] == null ? '' : `${i === 0 || rows[i-1][key] == null ? 'M' : 'L'} ${x(i)} ${y(r[key])}`).join(' ');
  return <><div className="trendlegend"><span><i/>{name}</span><span className="average"><i/>League average</span></div>
    <svg className="seasontrend" viewBox="0 0 590 225" role="img" aria-label={`Remaining weekly starter points for ${name}, compared with the league average. Exact values below.`}>
      {[0,.5,1].map(f => <g key={f}><line className="chartgrid" x1="42" x2="562" y1={y(low+span*f)} y2={y(low+span*f)}/><text x="32" y={y(low+span*f)+4} textAnchor="end">{Math.round(low+span*f)}</text></g>)}
      <path className="averageline" d={path('average')}/><path className="teamline" d={path('points')}/>
      {rows.map((r,i) => <g key={r.week}>{r.points != null && <circle className={r.missing ? 'coveragepoint' : 'teampoint'} cx={x(i)} cy={y(r.points)} r="4"><title>{`Week ${r.week}: ${points(r.points)} points${r.missing ? `; ${r.missing} starters missing projections` : ''}`}</title></circle>}<text x={x(i)} y="211" textAnchor="middle">{r.week}</text></g>)}
    </svg><p className="chartcaption">Scoring week · Optimized starters. Amber marks missing starter projections.</p></>;
}

export function LeagueView({data, Table}) {
  const [selected, setSelected] = useState(null);
  const teamId = data.teams.some(t => t.team_id === selected) ? selected : data.my_id;
  const team = data.outcomes.find(t => t.team_id === teamId);
  const record = data.standings.find(t => t.team_id === teamId);
  const trend = weeklyTrend(data, teamId);
  const complete = data.summary.current_scoring_period > data.summary.final_scoring_period;
  const maxWins = Math.max(1, ...data.standings.map(t => t.wins + .5*t.ties));
  const coverage = data.diagnostics.filter(r => r.team_id === teamId);
  const playoffCount = data.summary.playoff_team_count;
  return <>
    <div className="seasonintro"><div><span className="eyebrow">{complete ? 'THE FINAL PICTURE' : 'YOUR SEASON, PLAYED FORWARD'}</span><h2>{team?.team_name}</h2><p>Completed results plus optimized weekly lineups.</p></div>
      <label>Team perspective<select value={teamId} onChange={e => setSelected(Number(e.target.value))}>{data.teams.map(t => <option key={t.team_id} value={t.team_id}>{t.team_name}{t.team_id === data.my_id ? ' · You' : ''}</option>)}</select></label>
    </div>
    <div className="seasonsummary">
      <SummaryCard label={complete ? 'Final record' : 'Projected record'} value={record?.record ?? '—'} note={`${record?.actual_games ?? 0} completed · ${record?.projected_games ?? 0} projected games`}/>
      <SummaryCard label="Regular-season seed" value={team ? `#${team.seed}` : '—'} note={playoffCount ? `${playoffCount} playoff spots` : 'No postseason configured'}/>
      <SummaryCard label={complete ? 'Final finish' : 'Projected finish'} value={team ? `#${team.final_place}` : '—'} note={team?.playoff_result.replaceAll('_', ' ').toLowerCase()}/>
      <SummaryCard label="Remaining starter points" value={points(team?.remaining_points)} note={`${trend.filter(r => r.points != null).length} projected scoring weeks`}/>
    </div>
    <div className="seasoncontext"><span className="badge qualified">Deterministic scenario</span><p>{complete ? 'Champion' : 'Projected champion'}: <strong>{data.summary.champion_team}</strong>. Outcomes use ESPN point projections; run the Simulation view for outcome probabilities.</p></div>
    <div className="seasonvisuals">
      <section className="leaguerace"><div className="sectionhead"><h2>The league race</h2><small>WINS + ½ TIES</small></div><p className="muted">Select a team to explore its scoring outlook.</p>
        {data.standings.map((r,i) => <React.Fragment key={r.team_id}>{playoffCount > 0 && i === playoffCount && <div className="playoffcut">Playoff cutoff</div>}
          <button className={`racerow ${r.team_id === teamId ? 'selectedrace' : ''}`} aria-pressed={r.team_id === teamId} onClick={() => setSelected(r.team_id)}>
            <span className="raceseed">{r.seed}</span><span className="raceidentity">{r.team_name}{r.team_id === data.my_id && <small>YOUR TEAM</small>}<span className="track"><i style={{width:`${(r.wins+.5*r.ties)/maxWins*100}%`}}/></span></span><span className="racerecord">{r.record}<small>{points(r.points_for)} pts</small></span>
          </button></React.Fragment>)}
      </section>
      <div><section className="scoringoutlook"><span className="eyebrow">WHERE THE POINTS COME FROM</span><h2>Weekly scoring outlook</h2><ScoringTrend rows={trend} name={team?.team_name}/><details><summary>Exact weekly points</summary><Table rows={trend.map(r => ({Week:r.week,'Starter points':r.points,'League average':r.average,'Missing starter projections':r.points == null ? '—' : r.missing}))}/></details></section>
        <section className="coveragecard"><span className="eyebrow">PROJECTION COVERAGE</span><h2>{coverage.length ? `${coverage.length} player-weeks missing` : 'No missing projections'}</h2><p className="muted">{coverage.filter(r => r.starter).length} affect this team's optimized starters. Missing values count as zero; a missing value does not establish a bye.</p>{coverage.length > 0 && <details><summary>Inspect missing projections</summary><Table rows={coverage.map(r => ({Week:r.week,Player:r.player_name,Starter:r.starter ? 'Yes' : 'No','Assumed points':r.assumed_points}))}/></details>}</section>
      </div>
    </div>
    <details className="seasonstandings"><summary>Detailed league standings</summary><Table rows={standingsDetail(data)}/></details>
    <details><summary>Model rules and assumptions</summary><p className="muted">Effective week {data.summary.effective_week}. Standings rank by winning percentage (ties count as half a win), then points scored.</p><ul className="modelnotes">{data.summary.assumptions.map(note => <li key={note}>{note}</li>)}</ul></details>
  </>;
}
