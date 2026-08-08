import type {
	BattleHumanInterjectionPanelItem,
	BattleHumanInterjectionPanelSource,
	BattleHumanInterjectionState,
	BattleNormalizedUxFixture,
} from "./battle-types";

export type BattleHumanInterjectionPanelViewModel = {
	status: "receipt_bound" | "unavailable" | "missing_backend";
	sourceBound: boolean;
	runId: string | null;
	sourceProofReceipt: string | null;
	states: BattleHumanInterjectionPanelItem[];
	stateSet: BattleHumanInterjectionState[] | ["missing_backend"];
	reason: string | null;
	mocked: boolean | null;
	live: boolean | null;
};

const STATE_ORDER: BattleHumanInterjectionState[] = ["pending", "accepted", "applied", "rejected", "unavailable"];

function orderedStates(states: BattleHumanInterjectionPanelItem[]): BattleHumanInterjectionState[] {
	const present = new Set(states.map((state) => state.state));
	return STATE_ORDER.filter((state) => present.has(state));
}

function isReceiptBound(panel: BattleHumanInterjectionPanelSource): boolean {
	return panel.schema === "battle.human_interjection_panel.v1" && panel.source === "backend_receipts" && panel.live === true && panel.mocked === false;
}

export function humanInterjectionPanelViewModel(
	fixture: BattleNormalizedUxFixture | null | undefined,
): BattleHumanInterjectionPanelViewModel {
	const panel = fixture?.human_interjection_panel;
	if (!panel) {
		return {
			status: "missing_backend",
			sourceBound: false,
			runId: fixture?.run_id ?? null,
			sourceProofReceipt: null,
			states: [],
			stateSet: ["missing_backend"],
			reason: "No pause_after_round backend receipts are present in this fixture.",
			mocked: fixture?.mocked ?? null,
			live: fixture?.mocked === false ? true : null,
		};
	}

	if (!isReceiptBound(panel)) {
		return {
			status: "unavailable",
			sourceBound: false,
			runId: panel.run_id ?? fixture?.run_id ?? null,
			sourceProofReceipt: panel.source_proof_receipt ?? null,
			states: panel.states ?? [],
			stateSet: ["unavailable"],
			reason: "pause_after_round controls are unavailable because the panel source is not a live backend receipt set.",
			mocked: panel.mocked,
			live: panel.live,
		};
	}

	const states = panel.states ?? [];
	const stateSet = orderedStates(states);
	const hasOnlyUnavailable = stateSet.length === 1 && stateSet[0] === "unavailable";
	return {
		status: hasOnlyUnavailable ? "unavailable" : "receipt_bound",
		sourceBound: true,
		runId: panel.run_id ?? fixture?.run_id ?? null,
		sourceProofReceipt: panel.source_proof_receipt ?? null,
		states,
		stateSet: stateSet.length ? stateSet : ["unavailable"],
		reason: hasOnlyUnavailable ? states[0]?.label ?? "pause_after_round backend receipts are unavailable." : null,
		mocked: panel.mocked,
		live: panel.live,
	};
}
