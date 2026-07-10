import type { PopulationViewModel } from "../lib/battle-population-view-model";
import { BattleProofNav } from "../proof-card/BattleProofNav";
import { FitnessVectorPanel } from "./FitnessVectorPanel";
import { GenerationScrubber } from "./GenerationScrubber";
import { LineageTree } from "./LineageTree";
import { PopulationClaimBoundaryPanel } from "./PopulationClaimBoundaryPanel";
import { PopulationGrid } from "./PopulationGrid";
import { PopulationReceiptPanel } from "./PopulationReceiptPanel";
import { PopulationStatusHeader } from "./PopulationStatusHeader";
import { SelectionDecisionPanel } from "./SelectionDecisionPanel";
import "../proof-card/battle-proof-card.css";
import "./battle-population.css";

export function BattlePopulationPage({
	model,
	selectedGeneration,
	onSelectGeneration,
}: {
	model: PopulationViewModel;
	selectedGeneration: number | null;
	onSelectGeneration: (generation: number | null) => void;
}) {
	return (
		<div className="battle-proof-card battle-population h-full overflow-auto p-4" data-qid="battle:population:root">
			<BattleProofNav />
			<div className="mx-auto grid max-w-6xl gap-4">
				<PopulationStatusHeader model={model} />
				<GenerationScrubber
					generations={model.generations}
					selectedGeneration={selectedGeneration}
					onSelect={onSelectGeneration}
				/>
				<PopulationGrid specimens={model.specimens} />
				<LineageTree edges={model.edges} summary={model.lineageSummary} />
				<div className="grid gap-4 xl:grid-cols-2">
					<FitnessVectorPanel specimens={model.specimens} />
					<SelectionDecisionPanel specimens={model.specimens} />
				</div>
				<PopulationClaimBoundaryPanel model={model.claimBoundary} />
				<PopulationReceiptPanel receipts={model.receipts} />
			</div>
		</div>
	);
}
