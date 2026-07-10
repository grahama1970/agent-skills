import type { SynthesisViewModel } from "../lib/battle-synthesis-view-model";

export function GenomeToCodeTrace({
	genome,
	specimen,
	focused,
}: {
	genome: SynthesisViewModel["genome"];
	specimen: SynthesisViewModel["specimen"];
	focused?: boolean;
}) {
	return (
		<section className="battle-proof-panel" data-qid="battle:synthesis:genome-trace" data-focused={focused ? "true" : undefined}>
			<div className="battle-label">Genome → code trace</div>
			<div className="mt-2 battle-proof-genome-banner" data-qid="battle:synthesis:genome:provider-authored">
				PROVIDER-AUTHORED SPECIMEN — NOT COMPILED / NOT EXECUTED
			</div>
			<div className="mt-3 grid gap-1 text-xs text-slate-400">
				<div>
					<span className="battle-label mr-2">genome created_by</span>
					<span className="font-mono text-slate-200">{genome.createdBy}</span>
				</div>
				<div>
					<span className="battle-label mr-2">specimen created_by</span>
					<span className="font-mono text-slate-200">{specimen.createdBy}</span>
				</div>
			</div>
			<div className="mt-4 grid gap-3 md:grid-cols-2">
				<div>
					<div className="battle-label mb-2">Selected methods</div>
					<ul className="space-y-1 text-sm text-slate-200" data-qid="battle:synthesis:genome:selected">
						{(genome.selected.length ? genome.selected : specimen.selectedMethods).map((id) => (
							<li key={id} className="rounded border border-white/10 bg-black/20 px-2 py-1 font-mono text-xs">
								{id}
							</li>
						))}
					</ul>
				</div>
				<div>
					<div className="battle-label mb-2">Deferred methods</div>
					<ul className="space-y-1 text-sm text-slate-200" data-qid="battle:synthesis:genome:deferred">
						{genome.deferred.map((id) => (
							<li key={id} className="rounded border border-amber-400/20 bg-amber-400/5 px-2 py-1 font-mono text-xs">
								{id}
							</li>
						))}
					</ul>
				</div>
			</div>
			<div className="mt-4">
				<div className="battle-label mb-2">Rationale</div>
				<p className="text-sm leading-6 text-slate-300" data-qid="battle:synthesis:genome:rationale">
					{genome.rationale}
				</p>
			</div>
		</section>
	);
}
