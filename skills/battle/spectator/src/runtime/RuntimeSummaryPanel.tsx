import type { RuntimeViewModel } from "../lib/battle-runtime-view-model";

export function RuntimeSummaryPanel({
	model,
	focused,
}: {
	model: RuntimeViewModel["summary"];
	focused?: boolean;
}) {
	return (
		<section className="battle-proof-panel" data-qid="battle:runtime:summary" data-focused={focused ? "true" : undefined}>
			<div className="battle-label">Runtime totals</div>
			<div className="mt-3 grid gap-2 text-sm text-slate-300 md:grid-cols-2">
				<div data-qid="battle:runtime:summary:generated">
					<span className="battle-label mr-2">generated</span>
					<span className="font-mono text-slate-100">{model.generated}</span>
				</div>
				<div>
					<span className="battle-label mr-2">compile failed</span>
					<span className="font-mono text-slate-100">{model.compileFailed}</span>
				</div>
				<div data-qid="battle:runtime:summary:runtime-failed">
					<span className="battle-label mr-2">runtime failed</span>
					<span className="font-mono text-slate-100">{model.runtimeFailed}</span>
				</div>
				<div data-qid="battle:runtime:summary:runnable-unproven">
					<span className="battle-label mr-2">runnable unproven</span>
					<span className="font-mono text-slate-100">{model.runnableUnproven}</span>
				</div>
				<div data-qid="battle:runtime:summary:target-unproven">
					<span className="battle-label mr-2">target contact unproven</span>
					<span className="font-mono text-slate-100">{model.targetContactUnproven}</span>
				</div>
				<div data-qid="battle:runtime:summary:best">
					<span className="battle-label mr-2">best specimen</span>
					<span className="font-mono text-slate-100">{model.bestSpecimenId}</span>
				</div>
			</div>
		</section>
	);
}
