import { Badge } from "../ui/badge";
import type { ProofCardNodeView } from "../lib/battle-proof-card-view-model";

function iconFor(treatment: ProofCardNodeView["treatment"]): string {
	if (treatment === "pass") return "✓";
	if (treatment === "blocked") return "!";
	if (treatment === "fail") return "×";
	if (treatment === "running") return "…";
	return "–";
}

function statusCopy(treatment: ProofCardNodeView["treatment"]): string {
	if (treatment === "pass") return "receipt emitted";
	if (treatment === "blocked") return "expected capability boundary";
	if (treatment === "fail") return "contract / policy failure";
	if (treatment === "running") return "in progress";
	return "not emitted";
}

function badgeVariant(treatment: ProofCardNodeView["treatment"]) {
	if (treatment === "pass") return "green" as const;
	if (treatment === "blocked") return "yellow" as const;
	if (treatment === "fail") return "red" as const;
	if (treatment === "running") return "purple" as const;
	return "default" as const;
}

export function ProofNodePipeline({
	nodes,
	onSelect,
}: {
	nodes: ProofCardNodeView[];
	onSelect: (node: ProofCardNodeView) => void;
}) {
	return (
		<section className="battle-proof-panel" data-qid="battle:proof-card:node-status" aria-label="Tau child DAG nodes">
			<div className="battle-label">Node pipeline</div>
			<div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
				{nodes.map((node) => (
					<button
						key={node.id}
						type="button"
						className="battle-proof-node"
						data-treatment={node.treatment}
						data-qid={`battle:proof-card:node:${node.id}`}
						data-battle-proof-node={node.id}
						title={`Focus ${node.label}`}
						onClick={() => onSelect(node)}
					>
						<span className="battle-proof-node-icon" aria-hidden="true">
							{iconFor(node.treatment)}
						</span>
						<span className="min-w-0">
							<span className="block text-sm font-semibold text-slate-100">{node.label}</span>
							<span className="mt-0.5 block truncate text-xs text-slate-500">{statusCopy(node.treatment)}</span>
							<span className="mt-0.5 block truncate font-mono text-[11px] text-slate-600">{node.verdict}</span>
						</span>
						<Badge variant={badgeVariant(node.treatment)}>{node.status}</Badge>
					</button>
				))}
			</div>
		</section>
	);
}
