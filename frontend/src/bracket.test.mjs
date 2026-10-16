import {test} from 'node:test';
import assert from 'node:assert/strict';
import {bracketLayout} from './bracket.mjs';
test('paths follow actual teams through byes, reseeding and placement games',()=>{
 const games=[{round:1,matchup:1,team_a_id:3,team_b_id:6},{round:1,matchup:2,team_a_id:4,team_b_id:5},{round:2,matchup:1,team_a_id:1,team_b_id:4},{round:2,matchup:2,team_a_id:2,team_b_id:3},{round:2,matchup:3,team_a_id:5,team_b_id:6}];
 const layout=bracketLayout(games);
 assert.deepEqual(layout.rounds,[1,2]);
 assert.equal(layout.edges.length,4);
 assert.equal(layout.edges.find(e=>e.team===4).from.game.matchup,2);
 assert.equal(layout.edges.find(e=>e.team===6).to.game.matchup,3);
 assert.ok(layout.nodes.every(n=>n.y+155<=layout.height));
});
test('consolation paths include winners and losers moving between games',()=>{
 const layout=bracketLayout([{round:1,matchup:1,team_a_id:7,team_b_id:8},{round:1,matchup:2,team_a_id:9,team_b_id:10},{round:2,matchup:1,team_a_id:7,team_b_id:9},{round:2,matchup:2,team_a_id:8,team_b_id:10}]);
 assert.equal(layout.edges.length,4);
 assert.equal(layout.edges.find(e=>e.team===8).to.game.matchup,2);
});
