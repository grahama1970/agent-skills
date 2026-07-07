import type { BattleNormalizedUxFixture, BattleRaceEngineMode, LaneEvent } from "../lib/battle-types";

const TERMINAL_EVENT_KINDS = new Set([
	"blocked",
	"blue_blast",
	"killed",
	"fastest_crash",
	"promoted",
	"handoff",
	"spawn",
] as LaneEvent["kind"][]);

export type PixiReceiptValidationGate = {
	receiptSafe: boolean;
	warning?: string;
};

export function pixiReceiptValidationGate(
	fixture: BattleNormalizedUxFixture,
	mode: BattleRaceEngineMode,
): PixiReceiptValidationGate {
	if (mode === "design_fixture") return { receiptSafe: true };

	const validation = fixture.validation;
	if (!validation) {
		return {
			receiptSafe: false,
			warning: "Fixture validation missing — Pixi terminal effects suppressed (fail-closed).",
		};
	}

	if (validation.fail_closed === false) return { receiptSafe: true };

	const derivedOk = validation.derived_from_canonical_events !== false;
	const terminalOk = validation.terminal_claims_receipt_backed !== false;
	const errors = Array.isArray(validation.errors) ? validation.errors : [];

	if (!derivedOk || !terminalOk || errors.length > 0) {
		const parts: string[] = [];
		if (!derivedOk) parts.push("lanes not derived from canonical events");
		if (!terminalOk) parts.push("terminal claims not receipt-backed");
		if (errors.length > 0) parts.push(`${errors.length} validation error(s)`);
		return {
			receiptSafe: false,
			warning: `Receipt validation failed (${parts.join("; ")}) — Pixi terminal effects suppressed.`,
		};
	}

	return { receiptSafe: true };
}

export function pixiAllowsTerminalEffect(
	event: LaneEvent,
	gate: PixiReceiptValidationGate,
	mode: BattleRaceEngineMode,
): boolean {
	if (mode === "design_fixture") return Boolean(event.proven);
	if (!gate.receiptSafe) return false;
	if (!event.proven) return false;
	return TERMINAL_EVENT_KINDS.has(event.kind);
}
