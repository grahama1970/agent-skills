import { useState } from "react";
import type { ProofCardViewModel } from "../lib/battle-proof-card-view-model";
import { BattleProofNav } from "./BattleProofNav";
import { ClaimBoundaryPanel } from "./ClaimBoundaryPanel";
import { CandidateMethodsPanel } from "./CandidateMethodsPanel";
import { ExploitGenomePanel } from "./ExploitGenomePanel";
import { ProofCardHeader } from "./ProofCardHeader";
import { ProofNodePipeline } from "./ProofNodePipeline";
import { ProofReceiptPanel } from "./ProofReceiptPanel";
import { ResearchEvidencePanel } from "./ResearchEvidencePanel";
import "./battle-proof-card.css";

export function BattleProofCardPage({ model }: { model: ProofCardViewModel }) {
	const [focusedPanel, setFocusedPanel] = useState<string | null>(null);

	function focusPanel(panelId: string) {
		setFocusedPanel(panelId);
		const el = document.querySelector(`[data-qid="${panelId}"]`);
		el?.scrollIntoView({ behavior: "smooth", block: "start" });
	}

	return (
		<div className="battle-proof-card h-full overflow-auto p-4" data-qid="battle:proof-card:root">
			<BattleProofNav />
			<div className="mx-auto grid max-w-6xl gap-4">
				<ProofCardHeader model={model} />
				<ProofNodePipeline nodes={model.nodes} onSelect={(node) => focusPanel(node.panelId)} />
				<div className="grid gap-4 xl:grid-cols-2">
					<ResearchEvidencePanel model={model.research} focused={focusedPanel === "battle:proof-card:research"} />
					<ExploitGenomePanel model={model.genome} focused={focusedPanel === "battle:proof-card:genome"} />
				</div>
				<CandidateMethodsPanel groups={model.methodGroups} />
				<ClaimBoundaryPanel model={model.claimBoundary} focused={focusedPanel === "battle:proof-card:claim-boundary"} />
				<ProofReceiptPanel receipts={model.receipts} focused={focusedPanel === "battle:proof-card:receipts"} />
			</div>
		</div>
	);
}
