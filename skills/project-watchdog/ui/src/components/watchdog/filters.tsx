import { GateBadge } from '../ui/badge';
import { Button } from '../ui/button';
import type { GateStatus, WatchdogFilter } from '../../types';

const filters: WatchdogFilter[] = ['ALL', 'FAIL', 'BLOCKED', 'NEEDS_ATTENTION', 'PASS', 'DRY_RUN', 'SKIPPED', 'UNKNOWN'];

export function WatchdogFilters({
  active,
  counts,
  onChange,
}: {
  active: WatchdogFilter;
  counts: Record<string, number>;
  onChange: (filter: WatchdogFilter) => void;
}) {
  return (
    <div className="sticky top-0 z-20 -mx-4 border-b border-white/10 bg-slate-950/90 px-4 py-3 backdrop-blur md:rounded-2xl md:border md:bg-slate-950/70" data-qid="watchdog:filters" data-qs-action="WATCHDOG_FILTERS" title="Filter project-watchdog rows by explicit gate status">
      <div className="flex gap-2 overflow-x-auto pb-1">
        {filters.map((filter) => (
          <Button
            key={filter}
            className={active === filter ? 'ring-2 ring-cyan-300/60' : ''}
            data-qid={`watchdog:filter:${filter.toLowerCase()}`}
            data-qs-action="WATCHDOG_SET_FILTER"
            title={`Show ${filter === 'ALL' ? 'all' : filter} watchdog rows`}
            onClick={() => onChange(filter)}
          >
            {filter === 'ALL' ? <span>ALL</span> : <GateBadge status={filter as GateStatus} />}
            <span className="ml-2 text-slate-400">{counts[filter] ?? 0}</span>
          </Button>
        ))}
      </div>
    </div>
  );
}
