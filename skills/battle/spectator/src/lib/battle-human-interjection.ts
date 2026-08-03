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
const OPERATOR_STATE_PRIORITY: Record<BattleHumanInterjectionState, number> = {
	applied: 5,
	accepted: 4,
	pending: 3,
	rejected: 2,
	unavailable: 1,
};
const DIAGNOSTIC_REJECTION_REASONS = new Set(["invalid_auth", "invalid_timing", "wrong_run"]);

function orderedStates(states: BattleHumanInterjectionPanelItem[]): BattleHumanInterjectionState[] {
	const present = new Set(states.map((state) => state.state));
	return STATE_ORDER.filter((state) => present.has(state));
}

function isReceiptBound(panel: BattleHumanInterjectionPanelSource): boolean {
	return panel.schema === "battle.human_interjection_panel.v1" && panel.source === "backend_receipts" && panel.live === true && panel.mocked === false;
}

function stateSortValue(item: BattleHumanInterjectionPanelItem): number {
	const index = STATE_ORDER.indexOf(item.state);
	return index === -1 ? STATE_ORDER.length : index;
}

function isDiagnosticRejection(item: BattleHumanInterjectionPanelItem): boolean {
	return item.state === "rejected" && DIAGNOSTIC_REJECTION_REASONS.has(item.reason_code ?? "");
}

export function humanInterjectionOperatorStates(
	states: BattleHumanInterjectionPanelItem[],
	activeRequestId?: string | null,
): BattleHumanInterjectionPanelItem[] {
	const byRequest = new Map<string, BattleHumanInterjectionPanelItem>();
	for (const item of states) {
		const key = item.request_id ?? `${item.state}:${item.status}:${item.reason_code ?? item.label}`;
		const current = byRequest.get(key);
		if (!current) {
			byRequest.set(key, item);
			continue;
		}
		const itemPriority = OPERATOR_STATE_PRIORITY[item.state] ?? 0;
		const currentPriority = OPERATOR_STATE_PRIORITY[current.state] ?? 0;
		if (itemPriority > currentPriority || (itemPriority === currentPriority && item.backend_receipt && !current.backend_receipt)) {
			byRequest.set(key, item);
		}
	}

	const deduped = Array.from(byRequest.values());
	const active = activeRequestId ? deduped.filter((item) => item.request_id === activeRequestId) : [];
	const candidateStates = active.length ? active : deduped;
	const hasPrimaryState = candidateStates.some((item) => item.state === "pending" || item.state === "accepted" || item.state === "applied");
	const visible = hasPrimaryState ? candidateStates.filter((item) => item.state !== "rejected") : candidateStates.filter((item) => !isDiagnosticRejection(item));
	return visible.sort((a, b) => stateSortValue(a) - stateSortValue(b));
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
