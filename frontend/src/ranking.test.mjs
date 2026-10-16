import {test} from 'node:test';
import assert from 'node:assert/strict';
import {rankMoves} from './ranking.mjs';
const filters={team:'',size:'',special:true,mutual:true,metric:'sustained_weekly_lineup_gain',minimum:0,direction:'desc'};
const base={evaluation_status:'VALID',partner_team_id:2,trade_type:'2-for-2',my_give_player_ids:'1,2',my_receive_player_ids:'3,4',my_avg_remaining_season_lineup_gain:3,partner_avg_remaining_season_lineup_gain:2,my_sustained_weekly_lineup_gain:2,partner_sustained_weekly_lineup_gain:1,my_projected_wins_change:1};
test('team, package, both-side and special-team filters',()=>{
 assert.equal(rankMoves([base],'trades',filters,{}).length,1);
 for(const change of [{team:'3'},{size:'1-for-1'},{minimum:4}])assert.equal(rankMoves([base],'trades',{...filters,...change},{}).length,0);
 assert.equal(rankMoves([base],'trades',{...filters,special:false},{4:{default_position_id:16}}).length,0);
 assert.equal(rankMoves([{...base,partner_sustained_weekly_lineup_gain:-1}],'trades',filters,{}).length,0);
});
test('metric and order change ranking without changing the source',()=>{
 const other={...base,my_sustained_weekly_lineup_gain:1,my_projected_wins_change:2};
 assert.equal(rankMoves([base,other],'trades',{...filters,metric:'projected_wins_change'},{} )[0].score,2);
 assert.equal(rankMoves([base,other],'trades',{...filters,direction:'asc'},{} )[0].score,1);
 assert.equal(base.score,undefined);
});
test('waivers exclude kicker drops and invalid results',()=>{
 const row={evaluation_status:'VALID',add_player_id:1,drop_player_id:2,team_avg_remaining_season_lineup_gain:2,team_sustained_weekly_lineup_gain:1};
 assert.equal(rankMoves([row],'waivers',{...filters,special:false},{2:{default_position_id:5}}).length,0);
 assert.equal(rankMoves([{...row,evaluation_status:'INVALID_LINEUP'}],'waivers',filters,{}).length,0);
});
test('typical-week ranking favors durable help over a one-week bye spike',()=>{
 const byeFill={...base,my_avg_remaining_season_lineup_gain:2.5,my_sustained_weekly_lineup_gain:0};
 const weeklyUpgrade={...base,my_avg_remaining_season_lineup_gain:1,my_sustained_weekly_lineup_gain:1};
 const ranked=rankMoves([byeFill,weeklyUpgrade],'trades',{...filters,mutual:false},{});
 assert.equal(ranked[0].my_sustained_weekly_lineup_gain,1);
});
test('the default positive threshold hides one-week-only waiver moves',()=>{
 const byeFill={evaluation_status:'VALID',add_player_id:1,drop_player_id:2,team_sustained_weekly_lineup_gain:0};
 const recurring={...byeFill,add_player_id:3,team_sustained_weekly_lineup_gain:.25};
 const ranked=rankMoves([byeFill,recurring],'waivers',{...filters,minimum:.01},{});
 assert.deepEqual(ranked.map(row=>row.add_player_id),[3]);
});
test('trade results filter by player and position on either trade side',()=>{
 const players={1:{default_position_id:1},2:{default_position_id:2},3:{default_position_id:3},4:{default_position_id:4}};
 assert.equal(rankMoves([base],'trades',{...filters,player:'3',playerScope:'receive'},players).length,1);
 assert.equal(rankMoves([base],'trades',{...filters,player:'3',playerScope:'send'},players).length,0);
 assert.equal(rankMoves([base],'trades',{...filters,position:'2',positionScope:'send'},players).length,1);
 assert.equal(rankMoves([base],'trades',{...filters,position:'2',positionScope:'receive'},players).length,0);
});
test('multiple independent stat ranges can constrain both sides',()=>{
 const statRanges=[{key:'my_avg_remaining_season_lineup_gain',min:'2.5',max:'3.5'},{key:'partner_sustained_weekly_lineup_gain',min:'.5',max:'1.5'}];
 assert.equal(rankMoves([base],'trades',{...filters,statRanges},{}).length,1);
 assert.equal(rankMoves([{...base,partner_sustained_weekly_lineup_gain:2}],'trades',{...filters,statRanges},{}).length,0);
});
test('computed week-count and probability-point stats are filterable',()=>{
 const row={...base,my_weekly_lineup_gains:[2,0,-1,3],my_mc_playoff_probability_change:.075};
 assert.equal(rankMoves([row],'trades',{...filters,statRanges:[{key:'my_positive_weeks',min:2,max:2},{key:'my_mc_playoff_probability_points',min:7,max:8}]},{}).length,1);
 assert.equal(rankMoves([row],'trades',{...filters,statRanges:[{key:'my_negative_weeks',max:0}]},{}).length,0);
});
