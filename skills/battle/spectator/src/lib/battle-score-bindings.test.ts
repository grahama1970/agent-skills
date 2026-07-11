import { describe, expect, it } from "vitest";
import { scoreTriggerForEffectCue, scoreTriggerForReceiptBeat } from "./battle-score-bindings";
import type { ReceiptBeat } from "./battle-receipt-beats";
import type { BattleEffectCue } from "./battle-types";

function beat(partial: Partial<ReceiptBeat> & Pick<ReceiptBeat, "kind">): ReceiptBeat {
	return {
		id: "b1",
		atSeconds: 1,
		importance: "hero",
		proofStatus: "receipt_backed",
		laneId: "lane-1",
		branchIds: ["lane-1"],
		eventId: "e1",
		receiptId: "r1",
		camera: { focusSeconds: 1, preRollMs: 0, postRollMs: 0, follow: false },
		react: {
			liveEvent: { notification: "n", prefix: "p", highlight: "h", highlightTone: "red" },
			deathCard: partial.kind === "killed" || partial.kind === "kill_impact",
			soundCue: "none",
		},
		pixi: { emphasis: "none" },
		...partial,
	};
}

describe("battle-score-bindings fail-closed", () => {
	it("maps confirmed terminal receipts to death stinger only", () => {
		expect(scoreTriggerForReceiptBeat(beat({ kind: "killed" }))).toEqual({
			kind: "cue",
			cueId: "exploit_death_stinger",
			reason: "receipt:killed",
		});
		const killImpact = scoreTriggerForReceiptBeat(beat({ kind: "kill_impact" }));
		expect(killImpact && killImpact.kind === "cue" ? killImpact.cueId : null).toBe("exploit_death_stinger");
	});

	it("does not infer death from blue_blast animation alone", () => {
		expect(
			scoreTriggerForReceiptBeat(
				beat({
					kind: "blue_blast",
					react: {
						liveEvent: { notification: "n", prefix: "p", highlight: "h", highlightTone: "blue" },
						deathCard: false,
						soundCue: "kill_cannon",
					},
				}),
			),
		).toBeNull();
	});

	it("maps Judge-backed success to victory stinger only", () => {
		const success = scoreTriggerForReceiptBeat(beat({ kind: "judge_exploit_success" }));
		expect(success && success.kind === "cue" ? success.cueId : null).toBe("exploit_victory_stinger");
		const promoted = scoreTriggerForReceiptBeat(beat({ kind: "genome_promoted" }));
		expect(promoted && promoted.kind === "cue" ? promoted.cueId : null).toBe("exploit_victory_stinger");
		expect(scoreTriggerForReceiptBeat(beat({ kind: "compile_passed" }))).toBeNull();
		expect(scoreTriggerForReceiptBeat(beat({ kind: "target_contact_unproven" }))).toBeNull();
	});

	it("maps spawn to motif entrance and research_started to loop", () => {
		expect(scoreTriggerForReceiptBeat(beat({ kind: "spawn" }))).toEqual({
			kind: "motif_entrance",
			reason: "receipt:spawn",
		});
		const lifecycle = scoreTriggerForReceiptBeat(beat({ kind: "research_started" }));
		expect(lifecycle && lifecycle.kind === "cue" ? lifecycle.cueId : null).toBe("live_arena_loop");
	});

	it("maps effect cues with the same fail-closed rules", () => {
		const killed: BattleEffectCue = {
			eventId: "e",
			laneId: "l",
			cue: "killed",
			atSeconds: 1,
			receiptId: "r",
			proofMode: "receipt_backed",
			soundCue: "kill_cannon",
		};
		const killedTrigger = scoreTriggerForEffectCue(killed);
		expect(killedTrigger && killedTrigger.kind === "cue" ? killedTrigger.cueId : null).toBe("exploit_death_stinger");
		const blast: BattleEffectCue = { ...killed, cue: "blue_blast", soundCue: "kill_cannon" };
		expect(scoreTriggerForEffectCue(blast)).toBeNull();
	});
});
