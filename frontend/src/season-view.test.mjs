import test from 'node:test';
import assert from 'node:assert/strict';
import {weeklyTrend, standingsDetail} from './season-view.mjs';

test('trend excludes completed scores and retains zero, negative, and missing coverage', () => {
  const data = {summary:{current_scoring_period:2}, weekly:[
    {team_id:1, week:1, projected_points:100, result_type:'ACTUAL'},
    {team_id:1, week:2, projected_points:0, result_type:'PROJECTED', missing_starters:1},
    {team_id:2, week:2, projected_points:-4, result_type:'PROJECTED'},
    {team_id:1, week:3, projected_points:15, result_type:'ACTUAL'},
    {team_id:2, week:3, projected_points:10, result_type:'PROJECTED'},
  ]};
  assert.deepEqual(weeklyTrend(data, 1), [
    {week:2, points:0, average:-2, missing:1},
    {week:3, points:null, average:10, missing:0},
  ]);
  assert.deepEqual(weeklyTrend({...data,summary:{current_scoring_period:4}},1), []);
});

test('standings keep exact engine values and join final place by team identity', () => {
  const data = {standings:[{seed:2,team_id:7,team_name:'Seven',record:'2-1-1',points_for:123.456,points_against:99,actual_games:2,projected_games:2}],outcomes:[{team_id:7,final_place:1}]};
  assert.equal(standingsDetail(data)[0]['Points for'],123.456);
  assert.equal(standingsDetail(data)[0]['Final place'],1);
});
