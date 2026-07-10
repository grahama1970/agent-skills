import type { CompileViewModel } from "../lib/battle-compile-view-model";

export function CodeDiffViewer({
	model,
	focused,
}: {
	model: CompileViewModel["versionDiff"];
	focused?: boolean;
}) {
	return (
		<section className="battle-proof-panel" data-qid="battle:compile:diff" data-focused={focused ? "true" : undefined}>
			<div className="battle-label">Version diff</div>
			<div className="mt-3 grid gap-2 text-sm text-slate-300">
				<div>
					<span className="battle-label mr-2">from → to</span>
					<span className="font-mono text-slate-100">
						{model.fromId} → {model.toId}
					</span>
				</div>
				<div data-qid="battle:compile:diff:same-hash">
					<span className="battle-label mr-2">same code hash</span>
					<span className="text-slate-100">{model.sameHash ? "yes" : "no"}</span>
				</div>
			</div>
			<div className="battle-proof-notice mt-3" data-qid="battle:compile:diff:summary">
				{model.summary}
			</div>
		</section>
	);
}
