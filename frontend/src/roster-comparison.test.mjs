import {test} from 'node:test';
import assert from 'node:assert/strict';
import {fillRosterToTarget,optimizePartialRoster,optimizeRosterScenario} from './roster-comparison-data.mjs';
test('partial roster optimization reports coverage and best eligible starters',()=>{
 const players={1:{eligible_slots:[2]},2:{eligible_slots:[2]},3:{eligible_slots:[4]}};
 const projections=[{player_id:1,week:1,projected_points:5},{player_id:2,week:1,projected_points:9},{player_id:3,week:1,projected_points:7}];
 assert.deepEqual(optimizePartialRoster(['1','2','3'],players,projections,[{slot_id:2},{slot_id:4},{slot_id:6}],[1]),[{week:1,points:16,filled:2,lineup:[{slotIndex:0,playerId:'2',points:9},{slotIndex:1,playerId:'3',points:7}],required:3}]);
});
test('waiver filling is explicit and stops at the requested roster size',()=>{
 const players={1:{eligible_slots:[2]},2:{eligible_slots:[2]},3:{eligible_slots:[2]}};
 const projections=[{player_id:2,week:1,projected_points:4},{player_id:3,week:1,projected_points:8}];
 assert.deepEqual(fillRosterToTarget(['1'],['2','3'],players,projections,[{slot_id:2}],[1],2),['1','3']);
});
test('special-team policy streams the best available option only on a listed bye',()=>{
 const players={1:{default_position_id:5,eligible_slots:[17]},2:{default_position_id:5,eligible_slots:[17]}};
 const projections=[{player_id:1,week:1,projected_points:0},{player_id:1,week:2,projected_points:5},{player_id:2,week:1,projected_points:10},{player_id:2,week:2,projected_points:9}];
 const rows=optimizeRosterScenario(['1'],['2'],players,projections,[{slot_id:17}],[1,2],{1:[1]},true);
 assert.deepEqual(rows.map(r=>[r.week,r.points,r.streamedIds]),[[1,10,['2']],[2,5,[]]]);
});
