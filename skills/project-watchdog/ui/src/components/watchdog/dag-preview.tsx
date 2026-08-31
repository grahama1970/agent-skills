import { GitBranch, Network, ReceiptText } from 'lucide-react';
import { compactPath } from '../../lib';
import type { TauDagLink } from '../../types';
import { Card } from '../ui/card';

export function DagPreview({ tauDag }: { tauDag: TauDagLink | null }) {
  if (!tauDag) {
    return (
      <Card className="bg-slate-900/70">
        <div className="flex items-center gap-3 text-slate-300">
          <ReceiptText className="h-5 w-5 text-slate-400" />
          <div>
            <p className="font-semibold text-white">No DAG expected</p>
            <p className="text-sm">This row is represented by its receipt chain only.</p>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Card className="bg-gradient-to-br from-cyan-950/60 to-slate-950">
      <div className="flex items-start gap-3">
        <Network className="mt-1 h-5 w-5 text-cyan-200" />
        <div className="min-w-0 space-y-3">
          <div>
            <p className="font-semibold text-white">Tau DAG {tauDag.available ? 'available' : 'not recorded'}</p>
            <p className="text-sm text-slate-300">{tauDag.viewer_hint}</p>
          </div>
          <dl className="grid gap-2 text-xs text-slate-300">
            <div>
              <dt className="text-slate-500">Run directory</dt>
              <dd className="truncate font-mono">{compactPath(tauDag.run_dir)}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Progress receipt</dt>
              <dd className="truncate font-mono">{compactPath(tauDag.progress_path)}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Stream monitor</dt>
              <dd className="truncate font-mono">{compactPath(tauDag.stream_monitor_path)}</dd>
            </div>
          </dl>
          {tauDag.available && (
            <div className="rounded-2xl border border-cyan-300/20 bg-cyan-300/10 p-3 text-xs text-cyan-100">
              <GitBranch className="mr-2 inline h-4 w-4" />
              Embed target: Tau React Flow viewer consumes the run directory/progress path; project-watchdog does not duplicate Tau orchestration.
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
