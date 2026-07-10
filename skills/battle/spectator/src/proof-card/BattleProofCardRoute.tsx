import { useBattleProofCardFixture } from "../hooks/useBattleProofCardFixture";
import { BattleProofCardPage } from "./BattleProofCardPage";
import { BattleProofNav } from "./BattleProofNav";
import { ProofCardErrorState } from "./ProofCardErrorState";
import "./battle-proof-card.css";

export function BattleProofCardRoute() {
	const { viewModel, error, loading } = useBattleProofCardFixture();

	if (loading) {
		return (
			<div className="battle-proof-card grid h-full place-items-center text-slate-300">
				Loading proof-card fixture…
			</div>
		);
	}

	if (error) {
		return (
			<div className="battle-proof-card h-full p-4">
				<BattleProofNav />
				<ProofCardErrorState error={error} />
			</div>
		);
	}

	if (!viewModel) {
		return (
			<div className="battle-proof-card grid h-full place-items-center text-slate-500">
				No proof-card fixture loaded.
			</div>
		);
	}

	return <BattleProofCardPage model={viewModel} />;
}
