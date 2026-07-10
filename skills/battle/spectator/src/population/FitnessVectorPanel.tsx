import type { PopulationViewModel } from "../lib/battle-population-view-model";

export function FitnessVectorPanel({ specimens }: { specimens: PopulationViewModel["specimens"] }) {
	return (
		<section className="battle-proof-panel" data-qid="battle:population:fitness">
			<div className="battle-label">Fitness vectors</div>
			<div className="mt-3 space-y-2">
				{specimens.map((specimen) => (
					<div key={specimen.id} className="rounded border border-white/10 bg-black/20 px-2 py-1.5 text-xs" data-qid={`battle:population:fitness:${specimen.id}`}>
						<div className="flex flex-wrap items-center justify-between gap-2">
							<span className="font-mono text-slate-200">{specimen.id}</span>
							<span className="text-slate-400">
								tier {specimen.fitnessTier} · {specimen.fitnessLabel}
							</span>
						</div>
						<div className="mt-1 text-slate-500">
							compile_ok={String(specimen.fitnessFlags.compileOk)} · runtime_ok={String(specimen.fitnessFlags.runtimeOk)} ·
							target_unproven={String(specimen.fitnessFlags.targetUnproven)} · judge_confirmed=
							{String(specimen.fitnessFlags.judgeConfirmed)}
						</div>
						<div className="mt-1 truncate font-mono text-[11px] text-slate-600">{specimen.noveltyHash}</div>
					</div>
				))}
			</div>
		</section>
	);
}
