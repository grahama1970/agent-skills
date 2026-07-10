import { Badge } from "../ui/badge";
import type { RuntimeViewModel } from "../lib/battle-runtime-view-model";

export function JudgeProgressPanel({
	model,
	focused,
}: {
	model: RuntimeViewModel["judge"];
	focused?: boolean;
}) {
	return (
		<section className="battle-proof-panel" data-qid="battle:runtime:judge" data-focused={focused ? "true" : undefined}>
			<div className="flex flex-wrap items-center justify-between gap-2">
				<div className="battle-label">Judge progression</div>
				<Badge variant="default" data-qid="battle:runtime:judge:status">
					{model.status}
				</Badge>
			</div>
			<div className="mt-3 grid gap-2 text-sm text-slate-300">
				<div data-qid="battle:runtime:judge:verified">
					<span className="battle-label mr-2">judge verified exploits</span>
					<span className="font-mono text-slate-100">{model.verifiedExploits}</span>
				</div>
				<div data-qid="battle:runtime:judge:progression">
					<span className="battle-label mr-2">progression</span>
					<span className="font-mono text-slate-100">{model.progression.join(" → ")}</span>
				</div>
			</div>
			{model.doesNotProve.length ? (
				<div className="mt-4" data-qid="battle:runtime:judge:does-not-prove">
					<div className="battle-label mb-2">Does not prove</div>
					<ul className="space-y-1 text-sm text-slate-300">
						{model.doesNotProve.map((item) => (
							<li key={item}>{item}</li>
						))}
					</ul>
				</div>
			) : null}
			<div className="battle-proof-notice mt-3">Only Judge-confirmed states may unlock victory, kill, or containment visuals.</div>
		</section>
	);
}
