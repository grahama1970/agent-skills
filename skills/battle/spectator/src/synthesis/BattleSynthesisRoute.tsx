import { useBattleSynthesisFixture } from "../hooks/useBattleSynthesisFixture";
import { BattleProofNav } from "../proof-card/BattleProofNav";
import { BattleSynthesisPage } from "./BattleSynthesisPage";
import { SynthesisErrorState } from "./SynthesisErrorState";
import "../proof-card/battle-proof-card.css";
import "./battle-synthesis.css";

export function BattleSynthesisRoute() {
	const { viewModel, error, loading } = useBattleSynthesisFixture();

	if (loading) {
		return (
			<div className="battle-proof-card battle-synthesis grid h-full place-items-center text-slate-300">
				Loading synthesis fixture…
			</div>
		);
	}

	if (error) {
		return (
			<div className="battle-proof-card battle-synthesis h-full p-4">
				<BattleProofNav />
				<SynthesisErrorState error={error} />
			</div>
		);
	}

	if (!viewModel) {
		return (
			<div className="battle-proof-card battle-synthesis grid h-full place-items-center text-slate-500">
				No synthesis fixture loaded.
			</div>
		);
	}

	return <BattleSynthesisPage model={viewModel} />;
}
