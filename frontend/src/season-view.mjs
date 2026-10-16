export function weeklyTrend(data, teamId) {
  const weeks = [...new Set(data.weekly.filter(r => r.week >= data.summary.current_scoring_period && r.result_type === 'PROJECTED').map(r => r.week))].sort((a, b) => a - b);
  return weeks.map(week => {
    const rows = data.weekly.filter(r => r.week === week && r.result_type === 'PROJECTED');
    const selected = rows.find(r => r.team_id === teamId);
    return {week, points: selected?.projected_points ?? null,
      average: rows.reduce((total, r) => total + r.projected_points, 0) / rows.length,
      missing: selected?.missing_starters ?? 0};
  });
}

export function standingsDetail(data) {
  return data.standings.map(r => ({Seed: r.seed, Team: r.team_name, Record: r.record,
    'Points for': r.points_for, 'Points against': r.points_against,
    'Completed games': r.actual_games, 'Projected games': r.projected_games,
    'Final place': data.outcomes.find(t => t.team_id === r.team_id)?.final_place}));
}
