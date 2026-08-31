import { issueLabel } from '../../lib';
import type { WatchdogItem } from '../../types';
import { GateBadge, Chip } from '../ui/badge';
import { Button } from '../ui/button';
import { Card } from '../ui/card';

export function MobileCards({ items, onSelect }: { items: WatchdogItem[]; onSelect: (item: WatchdogItem) => void }) {
  return (
    <div className="grid gap-3 lg:hidden" data-qid="watchdog:cards" data-qs-action="WATCHDOG_MOBILE_CARDS" title="Project-watchdog mobile card list">
      {items.map((item) => (
        <Card key={item.item_id} className="space-y-3 p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-slate-500">{item.action ?? item.kind}</p>
              <p className="font-semibold text-white">{issueLabel(item.repo, item.issue_number)}</p>
            </div>
            <GateBadge status={item.gate_status} />
          </div>
          <p className="line-clamp-3 text-sm leading-6 text-slate-300">{item.summary}</p>
          <div className="flex flex-wrap gap-1">
            {(item.targets.length ? item.targets : [item.project_id ?? item.kind]).map((target) => <Chip key={target}>{target}</Chip>)}
          </div>
          <Button
            className="w-full"
            data-qid={`watchdog:card:${item.item_id}`}
            data-qs-action="WATCHDOG_OPEN_CARD"
            title={`Open mobile details for ${issueLabel(item.repo, item.issue_number)}`}
            onClick={() => onSelect(item)}
          >
            Inspect receipts and DAG
          </Button>
        </Card>
      ))}
    </div>
  );
}
