import React from 'react';
import {tradeStatFilters} from './ranking.mjs';

const positions={1:'QB',2:'RB',3:'WR',4:'TE',5:'K',16:'D/ST'};
const Side=({value,onChange})=><select aria-label="Trade side" value={value||'any'} onChange={e=>onChange(e.target.value)}><option value="any">Either side</option><option value="send">You send</option><option value="receive">You receive</option></select>;

export function TradeResultFilters({filters,update,players,rows}){
 const involved=new Set((rows||[]).flatMap(r=>[...String(r.my_give_player_ids).split(','),...String(r.my_receive_player_ids).split(',')]));
 const choices=Object.values(players).filter(p=>involved.has(String(p.player_id))).sort((a,b)=>a.player_name.localeCompare(b.player_name));
 const ranges=filters.statRanges||[];
 const changeRange=(index,change)=>update('statRanges',ranges.map((r,i)=>i===index?{...r,...change}:r));
 const unused=Object.keys(tradeStatFilters).find(key=>!ranges.some(r=>r.key===key));
 return <details className="resultfilters" open><summary>More result filters</summary><div className="filters filteridentity">
  <label>Package size<select value={filters.size||''} onChange={e=>update('size',e.target.value)}><option value="">All sizes</option>{[1,2,3].flatMap(give=>[1,2,3].map(receive=>{const value=`${give}-for-${receive}`;return <option key={value} value={value}>{value}</option>}))}</select></label>
  <label>Player<select value={filters.player||''} onChange={e=>update('player',e.target.value)}><option value="">All players</option>{choices.map(p=><option key={p.player_id} value={p.player_id}>{p.player_name}</option>)}</select></label><label>Player is on<Side value={filters.playerScope} onChange={v=>update('playerScope',v)}/></label>
  <label>Position<select value={filters.position||''} onChange={e=>update('position',e.target.value)}><option value="">All positions</option>{Object.entries(positions).map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label><label>Position is on<Side value={filters.positionScope} onChange={v=>update('positionScope',v)}/></label>
 </div><div className="statranges">{ranges.map((range,index)=><div className="statrange" key={`${range.key}-${index}`}><label>Statistic<select value={range.key} onChange={e=>changeRange(index,{key:e.target.value})}>{Object.entries(tradeStatFilters).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label><label>Minimum<input aria-label={`${tradeStatFilters[range.key]} minimum`} type="number" step="0.1" value={range.min} onChange={e=>changeRange(index,{min:e.target.value})}/></label><label>Maximum<input aria-label={`${tradeStatFilters[range.key]} maximum`} type="number" step="0.1" value={range.max} onChange={e=>changeRange(index,{max:e.target.value})}/></label><button onClick={()=>update('statRanges',ranges.filter((_,i)=>i!==index))}>Remove</button></div>)}</div><div className="filteractions"><button disabled={!unused} onClick={()=>update('statRanges',[...ranges,{key:unused,min:'',max:''}])}>Add statistic filter</button>{(filters.player||filters.position||ranges.length>0)&&<button onClick={()=>{update('player','');update('position','');update('statRanges',[])}}>Clear advanced filters</button>}</div></details>;
}
