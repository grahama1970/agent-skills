import { useMemo } from 'react';
import { Background, Controls, ReactFlow, type Edge, type Node } from '@xyflow/react';
import { GitBranch, Network, ReceiptText } from 'lucide-react';
import { compactPath } from '../../lib';
import type { TauDagGraph, TauDagLink, TauDagNode } from '../../types';
import { Card } from '../ui/card';

export function DagPreview({ tauDag }: { tauDag: TauDagLink | null }) {
  const graph = tauDag?.graph ?? null;
  const flow = useMemo(() => buildFlow(graph), [graph]);

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
    <Card className="bg-gradient-to-br from-cyan-950/60 to-slate-950" data-qid="watchdog:dag-preview" data-qs-action="WATCHDOG_DAG_PREVIEW" title="Embedded Tau React Flow DAG preview for the selected watchdog receipt">
      <div className="flex items-start gap-3">
        <Network className="mt-1 h-5 w-5 text-cyan-200" />
        <div className="min-w-0 flex-1 space-y-3">
          <div>
            <p className="font-semibold text-white">Tau DAG {tauDag.available ? 'available' : 'not recorded'}</p>
            <p className="text-sm text-slate-300">{tauDag.viewer_hint}</p>
          </div>
          {flow.nodes.length > 0 && (
            <div className="h-72 overflow-hidden rounded-2xl border border-cyan-300/20 bg-slate-950/80" data-qid="watchdog:dag-flow" data-qs-action="WATCHDOG_INSPECT_DAG_FLOW" title="Read-only embedded Tau DAG graph rendered from real dag-progress and dag.json artifacts">
              <ReactFlow nodes={flow.nodes} edges={flow.edges} fitView nodesDraggable={false} nodesConnectable={false} elementsSelectable={false}>
                <Background />
                <Controls showInteractive={false} />
              </ReactFlow>
            </div>
          )}
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
              Embedded graph: {flow.nodes.length} Tau node(s), {flow.edges.length} edge(s), from the recorded progress/DAG artifacts.
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

function buildFlow(graph: TauDagGraph | null): { nodes: Node[]; edges: Edge[] } {
  if (!graph) return { nodes: [], edges: [] };
  const nodes = graph.nodes.map((node, index) => ({
    id: node.id,
    data: { label: labelFor(node) },
    position: positionFor(index),
    className: nodeClass(node.status),
  }));
  const edges = graph.edges.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target, animated: true }));
  return { nodes, edges };
}

function labelFor(node: TauDagNode) {
  return `${node.label}\n${node.status}`;
}

function positionFor(index: number) {
  const column = index % 2;
  const row = Math.floor(index / 2);
  return { x: column * 240, y: row * 110 };
}

function nodeClass(status: string) {
  if (status === 'COMPLETED') return 'border-emerald-300 bg-emerald-950 text-emerald-50';
  if (status === 'FAILED' || status === 'BLOCKED') return 'border-rose-300 bg-rose-950 text-rose-50';
  return 'border-cyan-300 bg-slate-900 text-cyan-50';
}
