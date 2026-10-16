export function comparisonRows(selected,projections,firstWeek,finalWeek){
 const lookup=new Map(projections.map(r=>[`${r.player_id}-${r.week}`,r.projected_points]));
 return Array.from({length:Math.max(0,finalWeek-firstWeek+1)},(_,index)=>{
  const week=firstWeek+index,row={week};
  selected.forEach(id=>{row[id]=lookup.get(`${id}-${week}`)??null});
  return row;
 });
}
