import type { CompileViewModel } from "../lib/battle-compile-view-model";

export function CompileAttemptCard({
	model,
	focused,
}: {
	model: CompileViewModel["compile"];
	focused?: boolean;
}) {
	return (
		<section className="battle-proof-panel" data-qid="battle:compile:attempt" data-focused={focused ? "true" : undefined}>
			<div className="battle-label">Compile attempt</div>
			<div className="mt-3 grid gap-2 text-sm text-slate-300">
				<div data-qid="battle:compile:attempt:status">
					<span className="battle-label mr-2">status</span>
					<span className="text-slate-100">{model.status}</span>
				</div>
				<div>
					<span className="battle-label mr-2">verdict</span>
					<span className="font-mono text-slate-100">{model.verdict}</span>
				</div>
				<div data-qid="battle:compile:attempt:compiler">
					<span className="battle-label mr-2">compiler</span>
					<span className="font-mono text-slate-100">{model.compiler}</span>
				</div>
				<div data-qid="battle:compile:attempt:flags">
					<span className="battle-label mr-2">attempted</span>
					<span className="text-slate-100">{model.attempted ? "yes" : "no"}</span>
					<span className="battle-label ml-3 mr-2">failed</span>
					<span className="text-slate-100">{model.failed ? "yes" : "no"}</span>
					<span className="battle-label ml-3 mr-2">passed</span>
					<span className="text-slate-100">{model.passed ? "yes" : "no"}</span>
				</div>
				<div>
					<span className="battle-label mr-2">source → compiled</span>
					<span className="font-mono text-slate-100">
						{model.sourceVersionId} → {model.compiledVersionId}
					</span>
				</div>
			</div>
			{model.doesNotProve.length ? (
				<div className="mt-4" data-qid="battle:compile:attempt:does-not-prove">
					<div className="battle-label mb-2">Does not prove</div>
					<ul className="space-y-1 text-sm text-slate-300">
						{model.doesNotProve.map((item) => (
							<li key={item}>{item}</li>
						))}
					</ul>
				</div>
			) : null}
		</section>
	);
}
