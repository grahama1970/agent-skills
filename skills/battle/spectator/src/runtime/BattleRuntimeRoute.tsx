import { useBattleRuntimeFixture } from "../hooks/useBattleRuntimeFixture";
import { BattleProofNav } from "../proof-card/BattleProofNav";
import { BattleRuntimePage } from "./BattleRuntimePage";
import { RuntimeErrorState } from "./RuntimeErrorState";
import "../proof-card/battle-proof-card.css";
import "./battle-runtime.css";

export function BattleRuntimeRoute() {
	const { viewModel, error, loading } = useBattleRuntimeFixture();

	if (loading) {
		return (
			<div className="battle-proof-card battle-runtime grid h-full place-items-center text-slate-300">
				Loading runtime fixture…
			</div>
		);
	}

	if (error) {
		return (
			<div className="battle-proof-card battle-runtime h-full p-4">
				<BattleProofNav />
				<RuntimeErrorState error={error} />
			</div>
		);
	}

	if (!viewModel) {
		return (
			<div className="battle-proof-card battle-runtime grid h-full place-items-center text-slate-500">
				No runtime fixture loaded.
			</div>
		);
	}

	return <BattleRuntimePage model={viewModel} />;
}
