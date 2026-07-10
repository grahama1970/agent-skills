import { Badge } from "../ui/badge";
import type { PopulationViewModel } from "../lib/battle-population-view-model";

export function LineageTree({
	edges,
	summary,
}: {
	edges: PopulationViewModel["edges"];
	summary: PopulationViewModel["lineageSummary"];
}) {
	return (
		<section className="battle-proof-panel" data-qid="battle:population:lineage">
			<div className="battle-label">Lineage tree</div>
			<div className="mt-2 grid gap-1 text-xs text-slate-400 md:grid-cols-4" data-qid="battle:population:lineage:summary">
				<div>parent-child: {summary.parentChild}</div>
				<div>recombination: {summary.recombination}</div>
				<div>promoted: {summary.promoted}</div>
				<div>abandoned: {summary.abandoned}</div>
			</div>
			<div className="mt-3 grid gap-2">
				{edges.map((edge) => (
					<div key={edge.id} className="battle-population-edge" data-qid={`battle:population:edge:${edge.id}`}>
						<div className="flex flex-wrap items-center justify-between gap-2">
							<div className="font-mono text-slate-200">
								{edge.fromId} → {edge.toId}
							</div>
							<div className="flex gap-1">
								<Badge variant="default">{edge.type}</Badge>
								{edge.abandoned ? <Badge variant="yellow">abandoned</Badge> : null}
								{edge.promoted ? <Badge variant="green">promoted</Badge> : null}
							</div>
						</div>
						<div className="mt-1 text-slate-500">{edge.spawnCause}</div>
						{edge.inheritedMethods.length ? (
							<div className="mt-1 font-mono text-[11px] text-slate-600">{edge.inheritedMethods.join(", ")}</div>
						) : null}
					</div>
				))}
			</div>
		</section>
	);
}
