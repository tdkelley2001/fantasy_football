export function bracketLayout(games) {
  const rounds=[...new Set(games.map(g=>Number(g.round)))].sort((a,b)=>a-b);
  const height=Math.max(300,...rounds.map(r=>games.filter(g=>Number(g.round)===r).length*190+65));
  const nodes=rounds.flatMap((round,col)=>{
    const group=games.filter(g=>Number(g.round)===round).sort((a,b)=>a.matchup-b.matchup);
    return group.map((game,i)=>({game,x:col*330,y:65+i*(height-65)/group.length,col}));
  });
  const edges=[];
  for(const node of nodes){
    for(const id of [node.game.team_a_id,node.game.team_b_id]){
      const previous=nodes.filter(n=>n.col<node.col&&[n.game.team_a_id,n.game.team_b_id].includes(id)).sort((a,b)=>b.col-a.col)[0];
      if(previous)edges.push({from:previous,to:node,team:id});
    }
  }
  return {rounds,nodes,edges,height,width:Math.max(300,rounds.length*330-30)};
}
