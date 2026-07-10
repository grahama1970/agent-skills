import type { PopulationViewModel } from "../lib/battle-population-view-model";

export function GenerationScrubber({
	generations,
	selectedGeneration,
	onSelect,
}: {
	generations: PopulationViewModel["generations"];
	selectedGeneration: number | null;
	onSelect: (generation: number | null) => void;
}) {
	return (
		<section className="battle-proof-panel" data-qid="battle:population:generations">
			<div className="flex flex-wrap items-center justify-between gap-2">
				<div className="battle-label">Generation scrubber</div>
				<button
					type="button"
					className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400"
					onClick={() => onSelect(null)}
					data-qid="battle:population:generations:all"
				>
					Show all
				</button>
			</div>
			<div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
				{generations.map((generation) => (
					<button
						key={generation.generation}
						type="button"
						className="battle-population-gen-btn"
						data-active={selectedGeneration === generation.generation ? "true" : undefined}
						data-qid={`battle:population:generation:${generation.generation}`}
						onClick={() => onSelect(generation.generation)}
					>
						<div className="text-sm font-semibold text-slate-100">Gen {generation.generation}</div>
						<div className="mt-1 text-xs text-slate-500">
							{generation.specimen_count} specimen · {generation.selected_count} selected
						</div>
						<div className="mt-1 font-mono text-[11px] text-slate-600">{generation.specimen_ids.join(", ")}</div>
					</button>
				))}
			</div>
		</section>
	);
}
