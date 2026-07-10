import type { PopulationViewModel } from "../lib/battle-population-view-model";

export function SelectionDecisionPanel({ specimens }: { specimens: PopulationViewModel["specimens"] }) {
	return (
		<section className="battle-proof-panel" data-qid="battle:population:selection">
			<div className="battle-label">Selection decisions</div>
			<div className="mt-3 space-y-2">
				{specimens.map((specimen) => (
					<div key={specimen.id} className="rounded border border-white/10 bg-black/20 px-2 py-1.5 text-sm" data-qid={`battle:population:selection:${specimen.id}`}>
						<div className="font-mono text-xs text-slate-300">{specimen.id}</div>
						<div className="mt-1 text-slate-200">{specimen.selectionStatus}</div>
						<div className="mt-1 text-xs leading-5 text-slate-500">{specimen.selectionReason}</div>
					</div>
				))}
			</div>
		</section>
	);
}
