import {test} from 'node:test';
import assert from 'node:assert/strict';
import {comparisonRows} from './player-comparison-data.mjs';

test('comparison aligns projections by player and week and retains missing values',()=>{
 const rows=comparisonRows(['1','2'],[{player_id:1,week:4,projected_points:12},{player_id:2,week:5,projected_points:9}],4,5);
 assert.deepEqual(rows,[{week:4,1:12,2:null},{week:5,1:null,2:9}]);
});
