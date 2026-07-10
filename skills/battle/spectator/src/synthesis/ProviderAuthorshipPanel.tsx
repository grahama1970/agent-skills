import type { SynthesisViewModel } from "../lib/battle-synthesis-view-model";

export function ProviderAuthorshipPanel({
	model,
	focused,
}: {
	model: SynthesisViewModel["provider"];
	focused?: boolean;
}) {
	return (
		<section className="battle-proof-panel" data-qid="battle:synthesis:authorship" data-focused={focused ? "true" : undefined}>
			<div className="battle-label">Provider authorship</div>
			<div className="mt-3 grid gap-2 text-sm text-slate-300">
				<div data-qid="battle:synthesis:authorship:provider">
					<span className="battle-label mr-2">observed provider</span>
					<span className="font-mono text-slate-100">{model.observedProvider}</span>
				</div>
				<div data-qid="battle:synthesis:authorship:model">
					<span className="battle-label mr-2">observed model</span>
					<span className="font-mono text-slate-100">{model.observedModel}</span>
				</div>
				<div>
					<span className="battle-label mr-2">authored_by</span>
					<span className="font-mono text-slate-100">{model.authoredBy}</span>
				</div>
				<div data-qid="battle:synthesis:authorship:provider-live">
					<span className="battle-label mr-2">provider_live</span>
					<span className="text-violet-200">{model.providerLive ? "true" : "false"}</span>
				</div>
				<div>
					<span className="battle-label mr-2">provider run id present</span>
					<span className="text-slate-100">{model.runIdPresent ? "yes" : "no"}</span>
				</div>
				<div>
					<span className="battle-label mr-2">provider session id present</span>
					<span className="text-slate-100">{model.sessionIdPresent ? "yes" : "no"}</span>
				</div>
				<div data-qid="battle:synthesis:authorship:code-sha">
					<span className="battle-label mr-2">code sha256</span>
					<span className="break-all font-mono text-[11px] text-slate-200">{model.codeSha256}</span>
				</div>
				<div>
					<span className="battle-label mr-2">code bytes</span>
					<span className="font-mono text-slate-100">{model.codeBytes}</span>
				</div>
			</div>
		</section>
	);
}
