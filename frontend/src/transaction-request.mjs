export function applySearchEffectiveWeek(page, body, data) {
  if (page === 'Trade Search') {
    const key = ids => [...(ids || [])].map(String).sort().join(',');
    const match = data?.trades?.find(row =>
      key(String(row.my_give_player_ids).split(',')) === key(body.give) &&
      key(String(row.my_receive_player_ids).split(',')) === key(body.receive));
    return match ? {...body, effective_week: match.current_scoring_week,
      my_drops:String(match.my_drop_player_ids||'').split(',').filter(Boolean),
      partner_drops:String(match.partner_drop_player_ids||'').split(',').filter(Boolean)} : body;
  }
  if (page === 'Waiver Search') {
    const match = data?.waivers?.find(row =>
      String(row.add_player_id) === String(body.add) &&
      String(row.drop_player_id) === String(body.drop));
    return match ? {...body, effective_week: match.current_scoring_week} : body;
  }
  return body;
}
