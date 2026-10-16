export const metrics = {sustained_weekly_lineup_gain:'Sustained weekly points',median_weekly_lineup_gain:'Median weekly points',avg_remaining_season_lineup_gain:'Total value / remaining week',current_week_lineup_gain:'This week points',playoff_window_total_lineup_gain:'Playoff total points',projected_wins_change:'Projected wins gained',regular_seed_improvement:'Seed improvement',final_place_improvement:'Final place improvement'};
export const tradeStatFilters = {
 my_sustained_weekly_lineup_gain:'Your sustained points / week',partner_sustained_weekly_lineup_gain:'Opponent sustained points / week',
 my_median_weekly_lineup_gain:'Your median points / week',partner_median_weekly_lineup_gain:'Opponent median points / week',
 my_total_remaining_season_lineup_gain:'Your ROS starter points',partner_total_remaining_season_lineup_gain:'Opponent ROS starter points',
 my_avg_remaining_season_lineup_gain:'Your raw points / week',partner_avg_remaining_season_lineup_gain:'Opponent raw points / week',
 my_current_week_lineup_gain:'Your points this week',partner_current_week_lineup_gain:'Opponent points this week',
 my_playoff_window_total_lineup_gain:'Your playoff-window points',partner_playoff_window_total_lineup_gain:'Opponent playoff-window points',
 my_projected_wins_change:'Your projected wins gained',partner_projected_wins_change:'Opponent projected wins gained',
 my_regular_seed_improvement:'Your seed improvement',partner_regular_seed_improvement:'Opponent seed improvement',
 my_final_place_improvement:'Your final-place improvement',partner_final_place_improvement:'Opponent final-place improvement',
 my_worst_week_gain:'Your worst-week points',partner_worst_week_gain:'Opponent worst-week points',my_weekly_swing:'Your weekly point swing',
 my_positive_weeks:'Your positive weeks',my_negative_weeks:'Your negative weeks',
 my_mc_playoff_probability_points:'Your playoff probability change (pp)',my_mc_championship_probability_points:'Your title probability change (pp)'
};
const tradeIds=(r,scope='any')=>scope==='send'?String(r.my_give_player_ids).split(','):scope==='receive'?String(r.my_receive_player_ids).split(','):[...String(r.my_give_player_ids).split(','),...String(r.my_receive_player_ids).split(',')];
function statValue(r,key){
 if(key==='my_positive_weeks')return (r.my_weekly_lineup_gains||[]).filter(v=>v>0).length;
 if(key==='my_negative_weeks')return (r.my_weekly_lineup_gains||[]).filter(v=>v<0).length;
 if(key==='my_weekly_swing'){const values=r.my_weekly_lineup_gains||[];return values.length?Math.max(...values)-Math.min(...values):0;}
 if(key==='my_mc_playoff_probability_points')return r.my_mc_playoff_probability_change==null?null:100*Number(r.my_mc_playoff_probability_change);
 if(key==='my_mc_championship_probability_points')return r.my_mc_championship_probability_change==null?null:100*Number(r.my_mc_championship_probability_change);
 return r[key]==null?null:Number(r[key]);
}
export function rankMoves(rows, kind, filters, players) {
 const prefix=kind==='trades'?'my':'team';
 const ids=r=>kind==='trades'?[...String(r.my_give_player_ids).split(','),...String(r.my_receive_player_ids).split(',')]:[r.add_player_id,r.drop_player_id];
 return rows.filter(r=>r.evaluation_status==='VALID')
 .filter(r=>!filters.team || String(r.partner_team_id)===filters.team)
 .filter(r=>!filters.size || r.trade_type===filters.size)
 .filter(r=>filters.special || !ids(r).some(id=>[5,16].includes(Number(players[id]?.default_position_id))))
 .filter(r=>!filters.mutual || kind!=='trades' || (r.my_sustained_weekly_lineup_gain>0 && r.partner_sustained_weekly_lineup_gain>0))
 .filter(r=>kind!=='trades' || !filters.player || tradeIds(r,filters.playerScope).includes(String(filters.player)))
 .filter(r=>kind!=='trades' || !filters.position || tradeIds(r,filters.positionScope).some(id=>String(players[id]?.default_position_id)===String(filters.position)))
 .filter(r=>kind!=='trades' || !(filters.statRanges||[]).some(({key,min,max})=>{const value=statValue(r,key);return value==null || (min!==''&&min!=null&&value<Number(min)) || (max!==''&&max!=null&&value>Number(max))}))
 .map(r=>({...r,score:Number(r[`${prefix}_${filters.metric}`]||0)}))
 .filter(r=>r.score>=Number(filters.minimum))
 .sort((a,b)=>filters.direction==='asc'?a.score-b.score:b.score-a.score);
}
