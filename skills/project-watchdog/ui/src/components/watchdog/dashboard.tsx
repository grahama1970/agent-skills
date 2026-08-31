import { useMemo, useState } from 'react';
import { Activity, Radar, RefreshCw } from 'lucide-react';
import type { WatchdogFilter, WatchdogItem, WatchdogSnapshot } from '../../types';
import { useRegisterAction } from '../../hooks/use-register-action';
import { compactPath } from '../../lib';
import { Button } from '../ui/button';
import { Card, CardTitle } from '../ui/card';
import { WatchdogFilters } from './filters';
import { ItemTable } from './item-table';
import { MobileCards } from './mobile-cards';
import { DetailPanel } from './detail-panel';

export function WatchdogDashboard({ snapshot, onRefresh }: { snapshot: WatchdogSnapshot; onRefresh: () => void }) {
  const [filter, setFilter] = useState<WatchdogFilter>('ALL');
  const [selected, setSelected] = useState<WatchdogItem | null>(snapshot.items[0] ?? null);

  useRegisterAction({ qid: 'watchdog:refresh', action: 'WATCHDOG_REFRESH_SNAPSHOT', title: 'Refresh project-watchdog snapshot' });
  useRegisterAction({ qid: 'watchdog:filters', action: 'WATCHDOG_FILTERS', title: 'Filter watchdog rows by gate status' });
  useRegisterAction({ qid: 'watchdog:detail', action: 'WATCHDOG_DETAIL', title: 'Inspect selected watchdog row' });

  const items = useMemo(() => {
    return filter === 'ALL' ? snapshot.items : snapshot.items.filter((item) => item.gate_status === filter);
  }, [filter, snapshot.items]);

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,#164e63_0,#020617_34rem)] px-4 py-6 text-slate-100 md:px-8">
      <header className="mx-auto max-w-7xl space-y-6">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <div className="max-w-3xl">
            <p className="mb-3 inline-flex items-center rounded-full border border-cyan-300/30 bg-cyan-300/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.25em] text-cyan-100">
              <Radar className="mr-2 h-4 w-4" /> Repair factory control tower
            </p>
            <h1 className="text-4xl font-semibold tracking-tight text-white md:text-6xl">Project Watchdog</h1>
            <p className="mt-4 text-base leading-7 text-slate-300 md:text-lg">
              Receipt-backed queue visibility for observe → classify → ticket → lease → repair → verify → deliver → close → learn.
            </p>
          </div>
          <Button
            tone="primary"
            data-qid="watchdog:refresh"
            data-qs-action="WATCHDOG_REFRESH_SNAPSHOT"
            title="Reload the latest project-watchdog UI snapshot JSON"
            onClick={onRefresh}
          >
            <RefreshCw className="mr-2 h-4 w-4" /> Refresh snapshot
          </Button>
        </div>
        <section className="grid gap-3 md:grid-cols-4">
          <Metric label="Gate failures" value={(snapshot.counts.FAIL ?? 0) + (snapshot.counts.BLOCKED ?? 0)} tone="danger" />
          <Metric label="Needs attention" value={snapshot.counts.NEEDS_ATTENTION ?? 0} tone="warn" />
          <Metric label="Passing" value={snapshot.counts.PASS ?? 0} tone="pass" />
          <Metric label="Receipts scanned" value={snapshot.items.length} tone="info" />
        </section>
        <Card className="grid gap-3 md:grid-cols-3">
          <Info label="Global state" value={String(snapshot.global_state.state ?? 'unknown')} />
          <Info label="Receipt root" value={compactPath(snapshot.source.receipt_root ?? null)} />
          <Info label="Lock" value={snapshot.lock_held ? 'held' : 'clear'} />
        </Card>
      </header>
      <section className="mx-auto mt-6 grid max-w-7xl gap-6 lg:grid-cols-[minmax(0,1fr)_26rem]">
        <div className="space-y-4">
          <WatchdogFilters active={filter} counts={snapshot.counts} onChange={setFilter} />
          <ItemTable items={items} selectedId={selected?.item_id ?? null} onSelect={setSelected} />
          <MobileCards items={items} onSelect={setSelected} />
          {snapshot.warnings.length > 0 && (
            <Card className="border-amber-300/20 bg-amber-950/30 text-sm text-amber-100">
              <CardTitle className="text-base">Snapshot warnings</CardTitle>
              <ul className="mt-2 list-disc pl-5">{snapshot.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
            </Card>
          )}
        </div>
        <DetailPanel item={selected} onClose={() => setSelected(null)} />
      </section>
    </main>
  );
}

function Metric({ label, value, tone }: { label: string; value: number; tone: 'danger' | 'warn' | 'pass' | 'info' }) {
  const toneClass = { danger: 'text-rose-200', warn: 'text-amber-200', pass: 'text-emerald-200', info: 'text-cyan-200' }[tone];
  return (
    <Card className="p-4">
      <p className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-slate-500"><Activity className="h-4 w-4" /> {label}</p>
      <p className={`mt-3 text-3xl font-semibold ${toneClass}`}>{value}</p>
    </Card>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-[0.2em] text-slate-500">{label}</p>
      <p className="mt-1 truncate font-mono text-sm text-slate-200">{value}</p>
    </div>
  );
}
