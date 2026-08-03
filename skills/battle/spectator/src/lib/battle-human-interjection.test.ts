import { describe, expect, it } from "vitest";
import type { BattleNormalizedUxFixture } from "./battle-types";
import { humanInterjectionOperatorStates, humanInterjectionPanelViewModel } from "./battle-human-interjection";

const baseFixture = {
	schema: "battle.normalized_ux_fixture.v1",
	battle_id: "battle-004",
	run_id: "run-1",
	proof_mode: "receipt_backed_fixture",
	generated_at: "2026-08-01T00:00:00Z",
	mocked: false,
	lanes: [],
	events: [],
	leaderboard: [],
	receipts: [],
} as unknown as BattleNormalizedUxFixture;

describe("humanInterjectionPanelViewModel", () => {
	it("fails closed when backend receipt fields are missing", () => {
		const model = humanInterjectionPanelViewModel(baseFixture);
		expect(model.status).toBe("missing_backend");
		expect(model.sourceBound).toBe(false);
		expect(model.stateSet).toEqual(["missing_backend"]);
	});

	it("orders receipt-derived pause_after_round states", () => {
		const model = humanInterjectionPanelViewModel({
			...baseFixture,
			human_interjection_panel: {
				schema: "battle.human_interjection_panel.v1",
				source: "backend_receipts",
				run_id: "run-1",
				mocked: false,
				live: true,
				source_proof_receipt: "/tmp/proof.json",
				states: [
					{ state: "rejected", status: "REJECTED", label: "rejected", backend_receipt: true, live: true, mocked: false },
					{ state: "pending", status: "ACCEPTED", label: "pending", backend_receipt: true, live: true, mocked: false },
					{ state: "applied", status: "APPLIED", label: "applied", backend_receipt: true, live: true, mocked: false },
				],
			},
		});
		expect(model.status).toBe("receipt_bound");
		expect(model.sourceBound).toBe(true);
		expect(model.stateSet).toEqual(["pending", "applied", "rejected"]);
	});

	it("marks non-live or mocked panel data unavailable", () => {
		const model = humanInterjectionPanelViewModel({
			...baseFixture,
			human_interjection_panel: {
				schema: "battle.human_interjection_panel.v1",
				source: "local_preview",
				run_id: "run-1",
				mocked: true,
				live: false,
				states: [],
			},
		});
		expect(model.status).toBe("unavailable");
		expect(model.sourceBound).toBe(false);
		expect(model.stateSet).toEqual(["unavailable"]);
	});

	it("dedupes backend pause states and removes diagnostic rejections from the operator view", () => {
		const states = humanInterjectionOperatorStates([
			{
				state: "applied",
				status: "APPLIED",
				label: "pause_after_round applied at the after-round boundary.",
				request_id: "pause-1",
				backend_receipt: true,
				live: true,
				mocked: false,
			},
			{
				state: "rejected",
				status: "REJECTED",
				label: "pause_after_round rejected: invalid_auth.",
				request_id: "bad-auth-proof",
				reason_code: "invalid_auth",
				backend_receipt: true,
				live: true,
				mocked: false,
			},
			{
				state: "applied",
				status: "APPLIED",
				label: "pause_after_round applied at the after-round boundary.",
				request_id: "pause-1",
				backend_receipt: true,
				live: true,
				mocked: false,
			},
			{
				state: "rejected",
				status: "REJECTED",
				label: "pause_after_round rejected: wrong_run.",
				request_id: "wrong-run-proof",
				reason_code: "wrong_run",
				backend_receipt: true,
				live: true,
				mocked: false,
			},
		]);

		expect(states).toHaveLength(1);
		expect(states[0]?.state).toBe("applied");
		expect(states[0]?.request_id).toBe("pause-1");
	});

	it("keeps a single non-diagnostic rejection visible when no primary pause state exists", () => {
		const states = humanInterjectionOperatorStates([
			{
				state: "rejected",
				status: "REJECTED",
				label: "pause_after_round rejected by backend policy.",
				request_id: "operator-request",
				reason_code: "policy",
				backend_receipt: true,
				live: true,
				mocked: false,
			},
		]);

		expect(states).toHaveLength(1);
		expect(states[0]?.state).toBe("rejected");
	});
});
