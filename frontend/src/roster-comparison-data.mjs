export function optimizePartialRoster(playerIds,players,projections,slots,weeks){
 const pointMap=new Map(projections.map(r=>[`${r.player_id}-${r.week}`,Number(r.projected_points||0)]));
 return weeks.map(week=>{
  const indexed=playerIds.map((id,index)=>({id,index})),eligible=slots.map(slot=>indexed.filter(({id})=>(players[id]?.eligible_slots||[]).includes(slot.slot_id)));
  const memo=new Map();
  const solve=(index,used)=>{
   if(index===slots.length)return {points:0,filled:0,lineup:[]};
   const key=`${index}-${used}`;if(memo.has(key))return memo.get(key);
   let best=solve(index+1,used);
   for(const {id,index:playerIndex} of eligible[index])if(!(used&(1n<<BigInt(playerIndex)))){
    const points=pointMap.get(`${id}-${week}`)||0,next=solve(index+1,used|(1n<<BigInt(playerIndex))),candidate={points:next.points+points,filled:next.filled+1,lineup:[...next.lineup,{slotIndex:index,playerId:id,points}]};
    if(candidate.points>best.points||candidate.points===best.points&&candidate.filled>best.filled)best=candidate;
   }
   memo.set(key,best);return best;
  };
  const result=solve(0,0n);return {week,...result,lineup:result.lineup.sort((a,b)=>a.slotIndex-b.slotIndex),required:slots.length};
 });
}

export function fillRosterToTarget(playerIds,availableIds,players,projections,slots,weeks,target=17,excludeSpecial=false){
 const raw=new Map();for(const row of projections)if(weeks.includes(row.week))raw.set(String(row.player_id),(raw.get(String(row.player_id))||0)+Number(row.projected_points||0));
 // Marginal lineup optimization is substantially more expensive than the raw
 // pre-rank. The top 40 remaining-value candidates retain a broad position
 // pool while bounding interactive scenario work.
 const result=[...playerIds],remaining=availableIds.filter(id=>!result.includes(id)&&(!excludeSpecial||![5,16].includes(Number(players[id]?.default_position_id)))).sort((a,b)=>(raw.get(b)||0)-(raw.get(a)||0)).slice(0,40);
 while(result.length<target&&remaining.length){
  let bestIndex=-1,bestScore=-Infinity;
  remaining.forEach((id,index)=>{const score=optimizePartialRoster([...result,id],players,projections,slots,weeks).reduce((n,r)=>n+r.points,0);if(score>bestScore){bestScore=score;bestIndex=index}});
  result.push(remaining.splice(bestIndex,1)[0]);
 }
 return result;
}

export function optimizeRosterScenario(playerIds,availableIds,players,projections,slots,weeks,byeWeeks={},streamSpecial=false){
 if(!streamSpecial)return optimizePartialRoster(playerIds,players,projections,slots,weeks);
 const projectionMap=new Map(projections.map(r=>[`${r.player_id}-${r.week}`,Number(r.projected_points||0)]));
 return weeks.map(week=>{
  const extras=[];
  for(const position of [5,16]){
   const rostered=playerIds.filter(id=>Number(players[id]?.default_position_id)===position);
   const allOnBye=rostered.length===0||rostered.every(id=>(byeWeeks[id]||byeWeeks[Number(id)]||[]).includes(week));
   if(!allOnBye)continue;
   const best=availableIds.filter(id=>Number(players[id]?.default_position_id)===position&&!(byeWeeks[id]||byeWeeks[Number(id)]||[]).includes(week)).sort((a,b)=>(projectionMap.get(`${b}-${week}`)||0)-(projectionMap.get(`${a}-${week}`)||0))[0];
   if(best)extras.push(best);
  }
  const row=optimizePartialRoster([...playerIds,...extras],players,projections,slots,[week])[0];
  return {...row,streamedIds:extras};
 });
}
