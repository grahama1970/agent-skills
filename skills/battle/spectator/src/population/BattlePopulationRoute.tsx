import { useBattlePopulationFixture } from "../hooks/useBattlePopulationFixture";
import { BattleProofNav } from "../proof-card/BattleProofNav";
import { BattlePopulationPage } from "./BattlePopulationPage";
import { PopulationErrorState } from "./PopulationErrorState";
import "../proof-card/battle-proof-card.css";
import "./battle-population.css";

export function BattlePopulationRoute() {
	const { viewModel, error, loading, selectedGeneration, setSelectedGeneration } = useBattlePopulationFixture();

	if (loading) {
		return (
			<div className="battle-proof-card battle-population grid h-full place-items-center text-slate-300">
				Loading population fixture…
			</div>
		);
	}

	if (error) {
		return (
			<div className="battle-proof-card battle-population h-full p-4">
				<BattleProofNav />
				<PopulationErrorState error={error} />
			</div>
		);
	}

	if (!viewModel) {
		return (
			<div className="battle-proof-card battle-population grid h-full place-items-center text-slate-500">
				No population fixture loaded.
			</div>
		);
	}

	return (
		<BattlePopulationPage
			model={viewModel}
			selectedGeneration={selectedGeneration}
			onSelectGeneration={setSelectedGeneration}
		/>
	);
}
