import { useBattleCompileFixture } from "../hooks/useBattleCompileFixture";
import { BattleProofNav } from "../proof-card/BattleProofNav";
import { BattleCompilePage } from "./BattleCompilePage";
import { CompileErrorState } from "./CompileErrorState";
import "../proof-card/battle-proof-card.css";
import "./battle-compile.css";

export function BattleCompileRoute() {
	const { viewModel, error, loading } = useBattleCompileFixture();

	if (loading) {
		return (
			<div className="battle-proof-card battle-compile grid h-full place-items-center text-slate-300">
				Loading compile fixture…
			</div>
		);
	}

	if (error) {
		return (
			<div className="battle-proof-card battle-compile h-full p-4">
				<BattleProofNav />
				<CompileErrorState error={error} />
			</div>
		);
	}

	if (!viewModel) {
		return (
			<div className="battle-proof-card battle-compile grid h-full place-items-center text-slate-500">
				No compile fixture loaded.
			</div>
		);
	}

	return <BattleCompilePage model={viewModel} />;
}
