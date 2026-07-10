import { Badge } from "../ui/badge";
import type { SynthesisNodeView } from "../lib/battle-synthesis-view-model";

function iconFor(treatment: SynthesisNodeView["treatment"]): string {
	if (treatment === "pass") return "✓";
	if (treatment === "blocked") return "!";
	if (treatment === "fail") return "×";
	return "–";
}

function statusCopy(treatment: SynthesisNodeView["treatment"]): string {
	if (treatment === "pass") return "receipt emitted";
	if (treatment === "blocked") return "expected capability boundary";
	if (treatment === "fail") return "contract / policy failure";
	return "not emitted";
}

function badgeVariant(treatment: SynthesisNodeView["treatment"]) {
	if (treatment === "pass") return "green" as const;
	if (treatment === "blocked") return "yellow" as const;
	if (treatment === "fail") return "red" as const;
	return "default" as const;
}

export function SynthesisNodePipeline({
	nodes,
	onSelect,
}: {
	nodes: SynthesisNodeView[];
	onSelect: (node: SynthesisNodeView) => void;
}) {
	return (
		<section className="battle-proof-panel" data-qid="battle:synthesis:node-status" aria-label="PR3c synthesis nodes">
			<div className="battle-label">Node pipeline</div>
			<div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
				{nodes.map((node) => (
					<button
						key={node.id}
						type="button"
						className="battle-proof-node"
						data-treatment={node.treatment}
						data-qid={`battle:synthesis:node:${node.id}`}
						data-battle-synthesis-node={node.id}
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
