import type { SynthesisViewModel } from "../lib/battle-synthesis-view-model";

export function PromptWorkOrderSummary({
	model,
	focused,
}: {
	model: SynthesisViewModel["provider"];
	focused?: boolean;
}) {
	return (
		<section className="battle-proof-panel" data-qid="battle:synthesis:work-order" data-focused={focused ? "true" : undefined}>
			<div className="battle-label">Work-order / provenance bindings</div>
			<div className="mt-3 grid gap-2 text-sm text-slate-300">
				<div>
					<span className="battle-label mr-2">requested provider</span>
					<span className="font-mono text-slate-100">{model.requestedProvider}</span>
				</div>
				<div>
					<span className="battle-label mr-2">requested model</span>
					<span className="font-mono text-slate-100">{model.requestedModel}</span>
				</div>
				<div data-qid="battle:synthesis:work-order:run-ref">
					<span className="battle-label mr-2">provider run ref sha256</span>
					<span className="break-all font-mono text-[11px] text-slate-200">{model.runRefSha256}</span>
				</div>
				<div data-qid="battle:synthesis:work-order:goal-hash">
					<span className="battle-label mr-2">goal hash bound</span>
					<span className="text-slate-100">{model.goalHashBound ? "yes" : "no"}</span>
				</div>
				<div data-qid="battle:synthesis:work-order:output-hash">
					<span className="battle-label mr-2">output hash bound</span>
					<span className="text-slate-100">{model.outputHashBound ? "yes" : "no"}</span>
				</div>
				<div>
					<span className="battle-label mr-2">claim boundary passed</span>
					<span className="text-slate-100">{model.claimBoundaryPassed ? "yes" : "no"}</span>
				</div>
			</div>
		</section>
	);
}
