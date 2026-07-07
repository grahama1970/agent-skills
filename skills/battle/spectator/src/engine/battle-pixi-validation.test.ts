import { describe, expect, it } from "vitest";
import type { BattleNormalizedUxFixture } from "../lib/battle-types";
import { pixiAllowsTerminalEffect, pixiReceiptValidationGate } from "./battle-pixi-validation";

const baseFixture = {
	validation: {
		fail_closed: true,
		derived_from_canonical_events: true,
		terminal_claims_receipt_backed: true,
		errors: [],
	},
} as BattleNormalizedUxFixture;

describe("pixiReceiptValidationGate", () => {
	it("allows design fixture mode", () => {
		expect(pixiReceiptValidationGate(baseFixture, "design_fixture").receiptSafe).toBe(true);
	});

	it("blocks receipt mode when validation missing", () => {
		const gate = pixiReceiptValidationGate({} as BattleNormalizedUxFixture, "receipt_replay");
		expect(gate.receiptSafe).toBe(false);
		expect(gate.warning).toMatch(/fail-closed/i);
	});

	it("blocks terminal effects when receipt gate fails", () => {
		const gate = pixiReceiptValidationGate({} as BattleNormalizedUxFixture, "receipt_replay");
		expect(
			pixiAllowsTerminalEffect({ id: "e1", kind: "killed", x: 50, label: "KILLED", proven: true }, gate, "receipt_replay"),
		).toBe(false);
	});
});
