import { ExternalLink, FileJson, ShieldAlert } from 'lucide-react';
import { compactPath, issueLabel } from '../../lib';
import type { WatchdogItem } from '../../types';
import { GateBadge, Chip } from '../ui/badge';
import { Button } from '../ui/button';
import { Card, CardTitle } from '../ui/card';
import { DagPreview } from './dag-preview';

export function DetailPanel({ item, onClose }: { item: WatchdogItem | null; onClose: () => void }) {
  if (!item) {
    return (
      <Card className="hidden min-h-[34rem] lg:block">
        <CardTitle>Select a row</CardTitle>
        <p className="mt-3 text-sm text-slate-400">Open a ticket, receipt, or Tau lane from the table to inspect its proof boundary.</p>
      </Card>
    );
  }

  return (
    <aside className="lg:sticky lg:top-24" data-qid="watchdog:detail" data-qs-action="WATCHDOG_DETAIL" title="Selected project-watchdog item details">
      <Card className="space-y-5 border-cyan-300/20 bg-slate-950/90">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-cyan-200">{item.action ?? item.kind}</p>
            <CardTitle>{issueLabel(item.repo, item.issue_number)}</CardTitle>
          </div>
          <Button data-qid="watchdog:detail:close" data-qs-action="WATCHDOG_CLOSE_DETAIL" title="Close selected watchdog detail" onClick={onClose}>
            Close
          </Button>
        </div>
        <div className="flex flex-wrap gap-2">
          <GateBadge status={item.gate_status} />
          {(item.targets ?? []).map((target) => <Chip key={target}>{target}</Chip>)}
          {item.stop_reason && <Chip>{item.stop_reason}</Chip>}
        </div>
        <p className="text-sm leading-6 text-slate-300">{item.summary}</p>
        {item.issue_url && (
          <a
            className="inline-flex items-center gap-2 text-sm text-cyan-200 underline-offset-4 hover:underline"
            href={item.issue_url}
            data-qid="watchdog:detail:issue-link"
            data-qs-action="WATCHDOG_OPEN_ISSUE"
            title="Open the GitHub issue for this watchdog row"
          >
            Open GitHub issue <ExternalLink className="h-4 w-4" />
          </a>
        )}
        <DagPreview tauDag={item.tau_dag} />
        <Card className="bg-slate-900/70">
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 text-amber-200" />
            <CardTitle className="text-base">Gate and triage</CardTitle>
          </div>
          <dl className="mt-4 grid gap-3 text-sm">
            <Row label="Code" value={item.triage?.code ?? 'not recorded'} />
            <Row label="Cause" value={item.triage?.cause ?? 'not recorded'} />
            <Row label="Next command" value={item.triage?.next_command ?? 'not recorded'} mono />
            <Row label="Recoverable" value={item.triage?.recoverable == null ? 'not recorded' : String(item.triage.recoverable)} />
          </dl>
        </Card>
        <Card className="bg-slate-900/70">
          <div className="flex items-center gap-2">
            <FileJson className="h-5 w-5 text-cyan-200" />
            <CardTitle className="text-base">Receipts</CardTitle>
          </div>
          <ul className="mt-3 space-y-2 text-xs text-slate-300">
            <li className="truncate font-mono">receipt: {compactPath(item.receipt_path)}</li>
            {(item.evidence_paths ?? []).slice(0, 6).map((path) => <li className="truncate font-mono" key={path}>evidence: {compactPath(path)}</li>)}
          </ul>
        </Card>
      </Card>
    </aside>
  );
}

function Row({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">{label}</dt>
      <dd className={mono ? 'mt-1 break-words font-mono text-xs text-slate-200' : 'mt-1 text-slate-200'}>{value}</dd>
    </div>
  );
}
