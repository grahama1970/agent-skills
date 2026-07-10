import { useState } from "react";
import type { CompileViewModel } from "../lib/battle-compile-view-model";
import { BattleProofNav } from "../proof-card/BattleProofNav";
import { CodeDiffViewer } from "./CodeDiffViewer";
import { CompileAttemptCard } from "./CompileAttemptCard";
import { CompileClaimBoundaryPanel } from "./CompileClaimBoundaryPanel";
import { CompileNodePipeline } from "./CompileNodePipeline";
import { CompileReceiptPanel } from "./CompileReceiptPanel";
import { CompileStatusHeader } from "./CompileStatusHeader";
import { CompilerStderrPanel } from "./CompilerStderrPanel";
import { RepairReceiptPanel } from "./RepairReceiptPanel";
import { SelectedVersionPanel } from "./SelectedVersionPanel";
import { SpecimenVersionTimeline } from "./SpecimenVersionTimeline";
import "../proof-card/battle-proof-card.css";
import "./battle-compile.css";

const NODE_PANEL: Record<string, string> = {
	"lineage-summarizer": "battle:compile:receipts",
	"research-scout": "battle:compile:receipts",
	"method-combiner": "battle:compile:versions",
	"exploit-code-author": "battle:compile:versions",
	"compile-repair": "battle:compile:attempt",
};

export function BattleCompilePage({ model }: { model: CompileViewModel }) {
	const [focusedPanel, setFocusedPanel] = useState<string | null>(null);

	function focusPanel(panelId: string) {
		setFocusedPanel(panelId);
		document.querySelector(`[data-qid="${panelId}"]`)?.scrollIntoView({ behavior: "smooth", block: "start" });
	}

	return (
		<div className="battle-proof-card battle-compile h-full overflow-auto p-4" data-qid="battle:compile:root">
			<BattleProofNav />
			<div className="mx-auto grid max-w-6xl gap-4">
				<CompileStatusHeader model={model} />
				<CompileNodePipeline nodes={model.nodes} onSelect={(node) => focusPanel(NODE_PANEL[node.id] ?? "battle:compile:attempt")} />
				<SpecimenVersionTimeline versions={model.versions} focused={focusedPanel === "battle:compile:versions"} />
				<div className="grid gap-4 xl:grid-cols-2">
					<CompileAttemptCard model={model.compile} focused={focusedPanel === "battle:compile:attempt"} />
					<SelectedVersionPanel model={model.selectedVersion} focused={focusedPanel === "battle:compile:selected"} />
				</div>
				<CompilerStderrPanel model={model.compile} focused={focusedPanel === "battle:compile:stderr"} />
				<div className="grid gap-4 xl:grid-cols-2">
					<RepairReceiptPanel model={model.repair} focused={focusedPanel === "battle:compile:repair"} />
					<CodeDiffViewer model={model.versionDiff} focused={focusedPanel === "battle:compile:diff"} />
				</div>
				<CompileClaimBoundaryPanel model={model.claimBoundary} focused={focusedPanel === "battle:compile:claim-boundary"} />
				<CompileReceiptPanel receipts={model.receipts} focused={focusedPanel === "battle:compile:receipts"} />
			</div>
		</div>
	);
}
