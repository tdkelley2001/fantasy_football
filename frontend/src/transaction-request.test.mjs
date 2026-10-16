import test from 'node:test';
import assert from 'node:assert/strict';
import {applySearchEffectiveWeek} from './transaction-request.mjs';

test('trade search detail retains the generation effective week', () => {
  const body={give:['2','1'],receive:['9']};
  const data={trades:[{my_give_player_ids:'1,2',my_receive_player_ids:'9',my_drop_player_ids:'4',partner_drop_player_ids:'8',current_scoring_week:7}]};
  const result=applySearchEffectiveWeek('Trade Search',body,data);
  assert.equal(result.effective_week,7);
  assert.deepEqual(result.my_drops,['4']);
  assert.deepEqual(result.partner_drops,['8']);
});

test('waiver search detail retains the generation effective week', () => {
  const body={kind:'waivers',add:9,drop:2};
  const data={waivers:[{add_player_id:9,drop_player_id:2,current_scoring_week:8}]};
  assert.equal(applySearchEffectiveWeek('Waiver Search',body,data).effective_week,8);
});

test('manual evaluations keep their explicit effective week', () => {
  const body={give:['1'],receive:['2'],effective_week:4};
  assert.equal(applySearchEffectiveWeek('Trade Evaluator',body,{trades:[]}),body);
});
