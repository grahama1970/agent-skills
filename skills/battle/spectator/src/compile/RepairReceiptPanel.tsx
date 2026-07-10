import type { CompileViewModel } from "../lib/battle-compile-view-model";

export function RepairReceiptPanel({
	model,
	focused,
}: {
	model: CompileViewModel["repair"];
	focused?: boolean;
}) {
	return (
		<section className="battle-proof-panel" data-qid="battle:compile:repair" data-focused={focused ? "true" : undefined}>
			<div className="battle-label">Repair status</div>
			<div className="mt-3 grid gap-2 text-sm text-slate-300">
				<div data-qid="battle:compile:repair:attempted">
					<span className="battle-label mr-2">repair attempted</span>
					<span className="text-slate-100">{model.attempted ? "yes" : "no"}</span>
				</div>
				<div data-qid="battle:compile:repair:exhausted">
					<span className="battle-label mr-2">repair exhausted</span>
					<span className="text-slate-100">{model.exhausted ? "yes" : "no"}</span>
				</div>
				<div>
					<span className="battle-label mr-2">attempt count</span>
					<span className="font-mono text-slate-100">{model.attemptCount}</span>
				</div>
				<div>
					<span className="battle-label mr-2">provider repair live</span>
					<span className="text-slate-100">{model.providerRepairLive ? "yes" : "no"}</span>
				</div>
			</div>
		</section>
	);
}
