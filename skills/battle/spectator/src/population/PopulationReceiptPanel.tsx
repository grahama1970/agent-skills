import { Badge } from "../ui/badge";
import type { PopulationViewModel } from "../lib/battle-population-view-model";

export function PopulationReceiptPanel({ receipts }: { receipts: PopulationViewModel["receipts"] }) {
	return (
		<section className="battle-proof-panel" data-qid="battle:population:receipts">
			<div className="battle-label">Receipt references</div>
			<div className="mt-2 space-y-1">
				{receipts.map((ref) => (
					<div key={ref.id} className="grid grid-cols-[1fr_auto_auto] items-center gap-2 rounded border border-white/10 bg-black/20 px-2 py-1.5 text-xs">
						<button type="button" className="truncate text-left font-mono text-slate-200" onClick={() => void navigator.clipboard?.writeText(ref.id)}>
							{ref.id}
						</button>
						<span className="truncate text-slate-500">{ref.schema ?? "not emitted"}</span>
						<Badge variant="default">{ref.status ?? "not emitted"}</Badge>
					</div>
				))}
			</div>
		</section>
	);
}
