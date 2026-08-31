import { ChevronRight } from 'lucide-react';
import { issueLabel } from '../../lib';
import type { WatchdogItem } from '../../types';
import { GateBadge, Chip } from '../ui/badge';
import { Button } from '../ui/button';

export function ItemTable({ items, selectedId, onSelect }: { items: WatchdogItem[]; selectedId: string | null; onSelect: (item: WatchdogItem) => void }) {
  return (
    <div className="hidden overflow-hidden rounded-3xl border border-white/10 lg:block" data-qid="watchdog:table" data-qs-action="WATCHDOG_TABLE" title="Project-watchdog desktop filterable table">
      <table className="min-w-full divide-y divide-white/10 text-left text-sm">
        <thead className="bg-white/[0.04] text-xs uppercase tracking-[0.2em] text-slate-400">
          <tr>
            <th className="px-4 py-3">Gate</th>
            <th className="px-4 py-3">Ticket / tick</th>
            <th className="px-4 py-3">Target</th>
            <th className="px-4 py-3">DAG</th>
            <th className="px-4 py-3">Updated</th>
            <th className="px-4 py-3"><span className="sr-only">Open</span></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-white/10 bg-slate-950/50">
          {items.map((item) => (
            <tr key={item.item_id} className={selectedId === item.item_id ? 'bg-cyan-300/10' : 'hover:bg-white/[0.03]'}>
              <td className="px-4 py-4"><GateBadge status={item.gate_status} /></td>
              <td className="max-w-[18rem] px-4 py-4">
                <p className="font-semibold text-white">{issueLabel(item.repo, item.issue_number)}</p>
                <p className="truncate text-xs text-slate-400">{item.summary}</p>
              </td>
              <td className="px-4 py-4">
                <div className="flex max-w-[18rem] flex-wrap gap-1">
                  {(item.targets.length ? item.targets : [item.project_id ?? item.kind]).map((target) => <Chip key={target}>{target}</Chip>)}
                </div>
              </td>
              <td className="px-4 py-4 text-xs text-slate-300">{item.tau_dag?.available ? 'Tau DAG' : item.tau_dag?.expected ? 'No DAG recorded' : 'Receipt chain'}</td>
              <td className="px-4 py-4 text-xs text-slate-400">{item.updated_at ? new Date(item.updated_at).toLocaleString() : 'unknown'}</td>
              <td className="px-4 py-4 text-right">
                <Button
                  data-qid={`watchdog:row:${item.item_id}`}
                  data-qs-action="WATCHDOG_OPEN_ROW"
                  title={`Open details for ${issueLabel(item.repo, item.issue_number)}`}
                  onClick={() => onSelect(item)}
                >
                  Inspect <ChevronRight className="ml-1 h-4 w-4" />
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
