import { describe, expect, it } from "vitest";
import type { BattleNormalizedUxFixture } from "./battle-types";
import { humanInterjectionPanelViewModel } from "./battle-human-interjection";

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
});
