import React, {useState} from 'react';

const number = v => Number(v || 0).toFixed(1);
const gain = v => `${v > 0 ? '+' : ''}${number(v)}`;
const initials = name => String(name || '?').split(/\s+/).slice(0,2).map(x=>x[0]).join('').toUpperCase();

function Sparkline({values=[],label='Weekly impact'}) {
  if (!values.length) return null;
  const width=180,height=42,pad=4,min=Math.min(0,...values),max=Math.max(0,...values),span=Math.max(1,max-min);
  const x=i=>pad+i*(width-pad*2)/Math.max(1,values.length-1),y=v=>height-pad-(v-min)/span*(height-pad*2);
  const path=values.map((v,i)=>`${i?'L':'M'} ${x(i)} ${y(v)}`).join(' ');
  return <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}><line x1={pad} x2={width-pad} y1={y(0)} y2={y(0)} className="sparkzero"/><path d={path}/>{values.map((v,i)=><circle key={i} cx={x(i)} cy={y(v)} r="2"><title>{gain(v)} points</title></circle>)}</svg>;
}

function PlayerStack({label,ids,names=[],pbutton}) {
  return <div className="playerstack"><small>{label}</small>{ids.filter(Boolean).map((id,index)=><div className="playerrow" key={id}><span className="playeravatar">{initials(names[index])}</span>{pbutton(id)}</div>)}</div>;
}

function CompactMoveTable({rows,trade,pbutton,inspect,busy,metric}) {
  const prefix=trade?'my':'team';
  return <div className="tablewrap compactmoves"><table><thead><tr><th>#</th><th>Move</th>{trade&&<th>Partner</th>}<th>{metric}</th><th>ROS / week</th><th>Monte Carlo</th><th/></tr></thead><tbody>{rows.map((r,i)=><tr key={r.trade_id||`${r.add_player_id}-${r.drop_player_id}`}><td>{i+1}</td><td>{trade?<>{String(r.my_give_player_ids).split(',').map(id=><React.Fragment key={id}>{pbutton(id)} </React.Fragment>)} <span className="muted">→</span> {String(r.my_receive_player_ids).split(',').map(id=><React.Fragment key={id}>{pbutton(id)} </React.Fragment>)}</>:<>{pbutton(r.drop_player_id)} <span className="muted">→</span> {pbutton(r.add_player_id)}</>}</td>{trade&&<td>{r.partner_team}</td>}<td className={r.score<0?'negative':'positive'}>{gain(r.score)}</td><td>{gain(r[`${prefix}_avg_remaining_season_lineup_gain`])}</td><td>{r.monte_carlo_status==='COMPLETE'?`${gain(100*r.my_mc_playoff_probability_change)} pp playoff`:'—'}</td><td><button disabled={busy} onClick={()=>inspect(r)}>Analyze</button></td></tr>)}</tbody></table></div>;
}

export function MoveCards({rows, trade, pbutton, inspect, busy, metric}) {
  const [view,setView]=useState('cards'),prefix=trade?'my':'team';
  return <><div className="resulttoolbar"><div><strong>{rows.length.toLocaleString()} ranked moves</strong><span className="muted">Decision summary first. Exact values remain available.</span></div><div className="viewtoggle" role="group" aria-label="Result layout"><button className={view==='cards'?'active':''} onClick={()=>setView('cards')}>Cards</button><button className={view==='table'?'active':''} onClick={()=>setView('table')}>Table</button></div></div>{view==='table'?<CompactMoveTable {...{rows,trade,pbutton,inspect,busy,metric}}/>:<div className="movecards">{rows.map((r,i)=>{
    const deltas=r[`${prefix}_weekly_lineup_gains`]||[],weeks=r[`${prefix}_weekly_weeks`]||[],swing=deltas.length?Math.max(...deltas)-Math.min(...deltas):0;
    return <article className="movecard" key={r.trade_id||`${r.add_player_id}-${r.drop_player_id}`}>
      <div className="cardrank"><span>{String(i+1).padStart(2,'0')}</span><div><small>{trade?'TRADE WITH':'WAIVER MOVE'}</small><strong>{trade?r.partner_team:r.add_availability_status||'Available player'}</strong></div><span className="badge">{trade?r.trade_type:'ADD / DROP'}</span></div>
      <div className="exchange"><PlayerStack label={trade?'YOU SEND':'DROP'} ids={trade?String(r.my_give_player_ids).split(','):[r.drop_player_id]} names={trade?String(r.my_give).split(' + '):[r.drop_player]} pbutton={pbutton}/><span className="exchangeicon">→</span><PlayerStack label={trade?'YOU RECEIVE':'ADD'} ids={trade?String(r.my_receive_player_ids).split(','):[r.add_player_id]} names={trade?String(r.my_receive).split(' + '):[r.add_player]} pbutton={pbutton}/></div>
      {trade&&(r.my_drop_player_ids||r.partner_drop_player_ids)&&<div className="resolution"><small>ROSTER RESOLUTION</small>{r.my_drop_player_ids&&<span>You drop {String(r.my_drop_player_ids).split(',').map(id=><React.Fragment key={id}>{pbutton(id)} </React.Fragment>)}</span>}{r.partner_drop_player_ids&&<span>{r.partner_team} drops {String(r.partner_drop_player_ids).split(',').map(id=><React.Fragment key={id}>{pbutton(id)} </React.Fragment>)}</span>}</div>}
      <div className="moveheadline"><div><small>{metric}</small><strong className={r.score<0?'negative':'positive'}>{gain(r.score)}</strong></div><div><small>WEEKLY SHAPE</small><Sparkline values={deltas} label={`Weekly impact from week ${weeks[0]||''}`}/></div></div>
      <div className="movestats"><div><strong>{gain(r[`${prefix}_total_remaining_season_lineup_gain`])}</strong><small>ROS starter pts</small></div><div><strong>{gain(r[`${prefix}_avg_remaining_season_lineup_gain`])}</strong><small>Raw pts / week</small></div><div><strong>{gain(r[`${prefix}_projected_wins_change`])}</strong><small>Projected wins</small></div></div>
      <div className="chiprow"><span className="badge">{trade?r.trade_type:'Waiver'}</span>{trade&&<span className={r.partner_sustained_weekly_lineup_gain>=0?'badge positive':'badge negative'}>Opponent {gain(r.partner_sustained_weekly_lineup_gain)} sustained / wk</span>}{swing>=5&&<span className="badge warning">High variance</span>}{r[`${prefix}_worst_week_gain`]<-1&&<span className="badge warning">Week {r[`${prefix}_worst_week`]} downside</span>}{r.monte_carlo_status==='COMPLETE'&&<><span className="badge positive">{gain(100*r.my_mc_playoff_probability_change)} pp playoff</span><span className="badge positive">{gain(100*r.my_mc_championship_probability_change)} pp title</span></>}</div>
      <div className="cardbottom"><span className="muted">{deltas.filter(v=>v>0).length} positive · {deltas.filter(v=>v<0).length} negative weeks</span><button className="analysisbutton" disabled={busy} onClick={()=>inspect(r)}>View analysis <span>→</span></button></div>
    </article>})}</div>}</>;
}

function ImpactHeatmap({rows}) {
  const weeks=[...new Set(rows.map(r=>r.week))].sort((a,b)=>a-b),slots=[...new Set(rows.map(r=>r.slot_name))];
  const value=(slot,week)=>rows.filter(r=>r.slot_name===slot&&r.week===week).reduce((n,r)=>n+Number(r.projected_points_change||0),0);
  const scale=Math.max(1,...rows.map(r=>Math.abs(Number(r.projected_points_change||0))));
  return <div className="heatmapwrap"><div className="impactheatmap" style={{gridTemplateColumns:`110px repeat(${weeks.length},minmax(48px,1fr))`}}><span/>{weeks.map(w=><small key={w}>W{w}</small>)}{slots.flatMap(slot=>[<strong key={`${slot}-label`}>{slot}</strong>,...weeks.map(week=>{const v=value(slot,week),alpha=.1+.75*Math.abs(v)/scale;return <span key={`${slot}-${week}`} className="heatcell" style={{background:v>0?`rgba(70,211,153,${alpha})`:v<0?`rgba(248,113,113,${alpha})`:'var(--surface-2)'}}><b>{Math.abs(v)<.05?'·':gain(v)}</b><title>{`${slot}, week ${week}: ${gain(v)} points`}</title></span>})])}</div></div>;
}

export function ImpactView({detail, pbutton, Table, myId}) {
  const teams=[...new Map(detail.weekly.map(r=>[r.team_id,r.team_name])).entries()];
  const [selected,setSelected]=useState(null),[selectedWeek,setSelectedWeek]=useState(null);
  const team=teams.some(([id])=>id===selected)?selected:teams[0]?.[0],weeks=detail.weekly.filter(r=>r.team_id===team);
  const week=weeks.some(r=>r.week===selectedWeek)?selectedWeek:weeks[0]?.week,total=weeks.reduce((n,r)=>n+r.projected_points_change,0);
  const lineup=detail.lineups.filter(r=>r.team_id===team&&r.week===week),heatrows=detail.lineups.filter(r=>r.team_id===team);
  return <><BothSides detail={detail} myId={myId} selectTeam={setSelected}/><section className="drawerblock"><div className="sectionhead"><div><span className="eyebrow">WEEKLY IMPACT</span><h2>Where the move changes your lineup</h2></div><label>Team<select value={team??''} onChange={e=>setSelected(Number(e.target.value))}>{teams.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label></div><div className="impactheadline"><strong className={total<0?'negative':'positive'}>{gain(total)}</strong><span>projected starter points<br/>over {weeks.length} remaining weeks</span></div><ImpactHeatmap rows={heatrows}/><p className="chartcaption">Weeks run left to right. Color intensity shows the projected change at each lineup position.</p></section><details open><summary>Weekly impact and lineup changes</summary><div className="weektiles">{weeks.map(r=><button className={week===r.week?'selectedweek':''} key={r.week} onClick={()=>setSelectedWeek(r.week)}><small>WEEK {r.week}</small><strong className={r.projected_points_change<0?'negative':'positive'}>{gain(r.projected_points_change)}</strong></button>)}</div><h3>Week {week} · {teams.find(([id])=>id===team)?.[1]}</h3><div className="lineupcards">{lineup.map((r,i)=><div className="lineupcard" key={i}><span className="badge">{r.slot_name}</span><div><small>BEFORE · {number(r.projected_points_before)} PTS</small>{pbutton(r.player_id_before)}</div><span>→</span><div><small>AFTER · {number(r.projected_points_after)} PTS</small>{pbutton(r.player_id_after)}</div><strong className={r.projected_points_change<0?'negative':'positive'}>{gain(r.projected_points_change)}</strong></div>)}</div></details><details><summary>Exact values and season outcome detail</summary><Table rows={detail.weekly}/><Table rows={detail.teams}/></details></>;
}

export function BothSides({detail, myId, selectTeam}) {
  if(detail.teams.length<2)return null;
  return <section className="bothsides"><div className="sectionhead"><div><span className="eyebrow">TWO-SIDED VALUE</span><h2>What each roster gets</h2></div></div><div className="visualcolumns">{detail.teams.map(t=>{const weeks=detail.weekly.filter(r=>r.team_id===t.team_id).sort((a,b)=>a.week-b.week),total=weeks.reduce((n,r)=>n+r.projected_points_change,0),good=weeks.filter(r=>r.projected_points_change>0).length,bad=weeks.filter(r=>r.projected_points_change<0).length;return <article key={t.team_id}><span className="teammark">{initials(t.team_name)}</span><small>{t.team_id===myId?'YOUR ROSTER':'TRADE PARTNER'}</small><h3>{t.team_name}</h3><div className="impactheadline"><strong className={total<0?'negative':'positive'}>{gain(total/weeks.length)}</strong><span>starter points<br/>per week</span></div><div className="deltaflow"><span>{t.wins_before.toFixed(1)}</span><i>→</i><span>{t.wins_after.toFixed(1)}</span><strong className={t.wins_change<0?'negative':'positive'}>{gain(t.wins_change)}</strong><small>EXPECTED WINS</small></div><Sparkline values={weeks.map(w=>w.projected_points_change)} label={`${t.team_name} weekly impact`}/><p className="muted">{good} improving weeks · {bad} declining weeks</p><button onClick={()=>selectTeam(t.team_id)}>Inspect weekly lineups →</button></article>})}</div></section>;
}
