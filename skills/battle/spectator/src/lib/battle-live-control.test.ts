import { describe, expect, it } from "vitest";
import { deriveBattleLivePauseControl } from "./battle-live-control";
import type { BattleHumanInterjectionPanelSource } from "./battle-types";

const panel: BattleHumanInterjectionPanelSource = {
	schema: "battle.human_interjection_panel.v1",
	source: "backend_receipts",
	run_id: "run-1",
	mocked: false,
	live: true,
	states: [],
	control: {
		schema: "battle.human_interjection_control.v1",
		enabled: true,
		action: "pause_after_round",
		endpoint: "/battle/live/battle-004/controls/pause-after-round",
		auth: "bearer",
		boundary: "round_running",
		run_id: "run-1",
	},
};

describe("deriveBattleLivePauseControl", () => {
	it("enables control only from a live backend panel with a base URL", () => {
		const state = deriveBattleLivePauseControl({ panel, baseUrl: "http://127.0.0.1:18765" });
		expect(state.available).toBe(true);
		expect(state.status).toBe("idle");
		expect(state.endpoint).toBe("/battle/live/battle-004/controls/pause-after-round");
	});

	it("fails closed without a live base URL", () => {
		const state = deriveBattleLivePauseControl({ panel, baseUrl: null });
		expect(state.available).toBe(false);
		expect(state.status).toBe("unavailable");
	});

	it("shows local pending until backend receipts replace it", () => {
		const state = deriveBattleLivePauseControl({
			panel,
			baseUrl: "http://127.0.0.1:18765",
			requestId: "pause-1",
			localPending: true,
		});
		expect(state.status).toBe("pending");
		expect(state.requestId).toBe("pause-1");
	});

	it("prefers applied backend receipts over local pending", () => {
		const state = deriveBattleLivePauseControl({
			panel: {
				...panel,
				states: [
					{
						state: "applied",
						status: "APPLIED",
						label: "applied",
						request_id: "pause-1",
						reason_code: "pause_after_round_applied",
						backend_receipt: true,
						live: true,
						mocked: false,
					},
				],
			},
			baseUrl: "http://127.0.0.1:18765",
			requestId: "pause-1",
			localPending: true,
		});
		expect(state.status).toBe("applied");
		expect(state.lastReceiptStatus).toBe("APPLIED");
	});
});
