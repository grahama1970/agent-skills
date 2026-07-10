import type { RuntimeViewModel } from "../lib/battle-runtime-view-model";
import { BattleProofNav } from "../proof-card/BattleProofNav";
import { DockerPolicyPanel } from "./DockerPolicyPanel";
import { JudgeProgressPanel } from "./JudgeProgressPanel";
import { RuntimeClaimBoundaryPanel } from "./RuntimeClaimBoundaryPanel";
import { RuntimeReceiptPanel } from "./RuntimeReceiptPanel";
import { RuntimeStatusHeader } from "./RuntimeStatusHeader";
import { RuntimeSummaryPanel } from "./RuntimeSummaryPanel";
import { SpecimenRunCards } from "./SpecimenRunCards";
import "../proof-card/battle-proof-card.css";
import "./battle-runtime.css";

export function BattleRuntimePage({ model }: { model: RuntimeViewModel }) {
	return (
		<div className="battle-proof-card battle-runtime h-full overflow-auto p-4" data-qid="battle:runtime:root">
			<BattleProofNav />
			<div className="mx-auto grid max-w-6xl gap-4">
				<RuntimeStatusHeader model={model} />
				<div className="grid gap-4 xl:grid-cols-2">
					<DockerPolicyPanel model={model.docker} />
					<RuntimeSummaryPanel model={model.summary} />
				</div>
				<SpecimenRunCards runs={model.runs} selectedRunId={model.selectedRunId} />
				<JudgeProgressPanel model={model.judge} />
				<RuntimeClaimBoundaryPanel model={model.claimBoundary} />
				<RuntimeReceiptPanel receipts={model.receipts} />
			</div>
		</div>
	);
}
