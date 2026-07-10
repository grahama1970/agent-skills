import { Badge } from "../ui/badge";
import type { PopulationViewModel } from "../lib/battle-population-view-model";

function statusVariant(status: string) {
	const upper = status.toUpperCase();
	if (upper.includes("FAILED") || upper.includes("FAIL")) return "red" as const;
	if (upper.includes("UNPROVEN") || upper.includes("NOT")) return "yellow" as const;
	if (upper.includes("PASSED") || upper.includes("PASS") || upper.includes("SELECTED")) return "green" as const;
	return "default" as const;
}

export function PopulationGrid({ specimens }: { specimens: PopulationViewModel["specimens"] }) {
	return (
		<section className="battle-proof-panel" data-qid="battle:population:grid">
			<div className="battle-label">Specimen cards</div>
			<div className="mt-3 grid gap-3 xl:grid-cols-2">
				{specimens.map((specimen) => (
					<article
						key={specimen.id}
						className="battle-population-card"
						data-best={specimen.selectedBest ? "true" : undefined}
						data-qid={`battle:population:specimen:${specimen.id}`}
					>
						<div className="flex flex-wrap items-center justify-between gap-2">
							<div>
								<div className="text-sm font-semibold text-slate-100">{specimen.id}</div>
								<div className="mt-0.5 text-xs text-slate-500">
									gen {specimen.generation}
									{specimen.parentId ? ` · parent ${specimen.parentId}` : " · root"}
								</div>
							</div>
							<div className="flex flex-wrap gap-1">
								{specimen.selectedBest ? <Badge variant="purple">best</Badge> : null}
								<Badge variant={statusVariant(specimen.runtimeStatus)}>{specimen.runtimeStatus}</Badge>
							</div>
						</div>
						<div className="mt-3 grid gap-1 text-xs text-slate-400">
							<div>
								<span className="battle-label mr-2">compile</span>
								<span className="text-slate-200">{specimen.compileStatus}</span>
							</div>
							<div data-qid={`battle:population:specimen:${specimen.id}:target`}>
								<span className="battle-label mr-2">target</span>
								<span className="text-slate-200">{specimen.targetStatus}</span>
							</div>
							<div>
								<span className="battle-label mr-2">judge</span>
								<span className="text-slate-200">{specimen.judgeStatus}</span>
								<span className="battle-label ml-3 mr-2">verified</span>
								<span className="font-mono text-slate-200">{specimen.judgeVerified}</span>
							</div>
							<div>
								<span className="battle-label mr-2">authored_by</span>
								<span className="font-mono text-slate-200">{specimen.providerAuthoredBy}</span>
								<span className="battle-label ml-3 mr-2">provider_live</span>
								<span className="text-slate-200">{specimen.providerLive ? "true" : "false"}</span>
							</div>
							<div data-qid={`battle:population:specimen:${specimen.id}:fitness`}>
								<span className="battle-label mr-2">fitness</span>
								<span className="text-slate-200">
									tier {specimen.fitnessTier} · {specimen.fitnessLabel}
								</span>
							</div>
							<div data-qid={`battle:population:specimen:${specimen.id}:selection`}>
								<span className="battle-label mr-2">selection</span>
								<span className="text-slate-200">{specimen.selectionStatus}</span>
							</div>
						</div>
						<div className="mt-3">
							<div className="battle-label mb-1">methods</div>
							<ul className="space-y-1 text-sm text-slate-300" data-qid={`battle:population:specimen:${specimen.id}:methods`}>
								{specimen.methods.map((method) => (
									<li key={method.id} className="font-mono text-xs">
										{method.name}
									</li>
								))}
							</ul>
						</div>
						<p className="mt-3 text-xs leading-5 text-slate-500">{specimen.selectionReason}</p>
					</article>
				))}
			</div>
		</section>
	);
}
