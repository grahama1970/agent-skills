import { useState } from "react";
import type { SynthesisViewModel } from "../lib/battle-synthesis-view-model";
import { BattleProofNav } from "../proof-card/BattleProofNav";
import { CodeArtifactViewer } from "./CodeArtifactViewer";
import { GenomeToCodeTrace } from "./GenomeToCodeTrace";
import { PromptWorkOrderSummary } from "./PromptWorkOrderSummary";
import { ProviderAuthorshipPanel } from "./ProviderAuthorshipPanel";
import { SynthesisClaimBoundaryPanel } from "./SynthesisClaimBoundaryPanel";
import { SynthesisNodePipeline } from "./SynthesisNodePipeline";
import { SynthesisReceiptPanel } from "./SynthesisReceiptPanel";
import { SynthesisStatusHeader } from "./SynthesisStatusHeader";
import "../proof-card/battle-proof-card.css";
import "./battle-synthesis.css";

const NODE_PANEL: Record<string, string> = {
	"lineage-summarizer": "battle:synthesis:receipts",
	"research-scout": "battle:synthesis:genome-trace",
	"method-combiner": "battle:synthesis:genome-trace",
	"exploit-code-author": "battle:synthesis:code",
};

export function BattleSynthesisPage({ model }: { model: SynthesisViewModel }) {
	const [focusedPanel, setFocusedPanel] = useState<string | null>(null);

	function focusPanel(panelId: string) {
		setFocusedPanel(panelId);
		const el = document.querySelector(`[data-qid="${panelId}"]`);
		el?.scrollIntoView({ behavior: "smooth", block: "start" });
	}

	return (
		<div className="battle-proof-card battle-synthesis h-full overflow-auto p-4" data-qid="battle:synthesis:root">
			<BattleProofNav />
			<div className="mx-auto grid max-w-6xl gap-4">
				<SynthesisStatusHeader model={model} />
				<SynthesisNodePipeline
					nodes={model.nodes}
					onSelect={(node) => focusPanel(NODE_PANEL[node.id] ?? "battle:synthesis:authorship")}
				/>
				<div className="grid gap-4 xl:grid-cols-2">
					<ProviderAuthorshipPanel model={model.provider} focused={focusedPanel === "battle:synthesis:authorship"} />
					<PromptWorkOrderSummary model={model.provider} focused={focusedPanel === "battle:synthesis:work-order"} />
				</div>
				<CodeArtifactViewer model={model.specimen} focused={focusedPanel === "battle:synthesis:code"} />
				<GenomeToCodeTrace
					genome={model.genome}
					specimen={model.specimen}
					focused={focusedPanel === "battle:synthesis:genome-trace"}
				/>
				<SynthesisClaimBoundaryPanel model={model.claimBoundary} focused={focusedPanel === "battle:synthesis:claim-boundary"} />
				<SynthesisReceiptPanel receipts={model.receipts} focused={focusedPanel === "battle:synthesis:receipts"} />
			</div>
		</div>
	);
}
