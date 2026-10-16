import React from 'react';

export function WorkProgress({progress}) {
  const counted = Number.isFinite(progress?.total) && progress.total > 0 && Number.isFinite(progress?.done);
  const done = counted ? Math.max(0, Math.min(progress.done, progress.total)) : 0;
  const percent = counted ? Math.floor(100 * done / progress.total) : null;
  const stage = progress?.stage || 'Loading…';
  return <section className="work-progress" aria-label="Analysis progress">
    <div className="work-progress-heading"><strong role="status">{stage}</strong><span>{counted ? `${percent}%` : 'Working…'}</span></div>
    <progress aria-label={stage} max={counted ? progress.total : 1} value={counted ? done : undefined}/>
    <small>{counted ? `${done.toLocaleString()} / ${progress.total.toLocaleString()} ${progress.unit} · Current stage` : 'This stage has no fixed count.'} · Updates automatically</small>
  </section>;
}
