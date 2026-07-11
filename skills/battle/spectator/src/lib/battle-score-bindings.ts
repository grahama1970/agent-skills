/**
 * Fail-closed score bindings: death / victory / arena progression only from
 * confirmed receipt-backed beats — never from animation drift alone.
 */
import type { BattleEffectCue } from "./battle-types";
import type { ReceiptBeat } from "./battle-receipt-beats";
import type { BattleScoreCueId } from "./battle-music-catalog";

const TERMINAL_KINDS = new Set(["kill_impact", "killed"]);
const VICTORY_KINDS = new Set(["judge_exploit_success", "genome_promoted"]);
const ENTRANCE_KINDS = new Set(["spawn"]);
const LIFECYCLE_KINDS = new Set(["research_started"]);
const ARENA_TRANSITION_KINDS = new Set(["scenario_loaded"]);

export type BattleScoreTrigger =
	| { kind: "cue"; cueId: BattleScoreCueId; reason: string }
	| { kind: "motif_entrance"; reason: string }
	| null;

/**
 * Map a receipt director beat to a score trigger. Returns null when unbound
 * (fail-closed — no speculative death/victory/arena music).
 */
export function scoreTriggerForReceiptBeat(beat: ReceiptBeat): BattleScoreTrigger {
	const kind = beat.kind;
	if (TERMINAL_KINDS.has(kind)) {
		return { kind: "cue", cueId: "exploit_death_stinger", reason: `receipt:${kind}` };
	}
	if (VICTORY_KINDS.has(kind)) {
		return { kind: "cue", cueId: "exploit_victory_stinger", reason: `receipt:${kind}` };
	}
	if (ENTRANCE_KINDS.has(kind)) {
		return { kind: "motif_entrance", reason: `receipt:${kind}` };
	}
	if (LIFECYCLE_KINDS.has(kind)) {
		return { kind: "cue", cueId: "live_arena_loop", reason: `receipt:${kind}` };
	}
	if (ARENA_TRANSITION_KINDS.has(kind)) {
		return { kind: "cue", cueId: "next_battle_arena", reason: `receipt:${kind}` };
	}
	return null;
}

/** Effect-cue path used by Pixi onEffectCue — same fail-closed rules. */
export function scoreTriggerForEffectCue(cue: BattleEffectCue): BattleScoreTrigger {
	const kind = String(cue.cue);
	if (kind === "killed" || kind === "kill_impact") {
		return { kind: "cue", cueId: "exploit_death_stinger", reason: `effect:${kind}` };
	}
	if (kind === "judge_exploit_success" || kind === "genome_promoted") {
		return { kind: "cue", cueId: "exploit_victory_stinger", reason: `effect:${kind}` };
	}
	if (kind === "spawn") {
		return { kind: "motif_entrance", reason: `effect:${kind}` };
	}
	// Do not map blue_blast / animation-only cues to terminal stingers.
	return null;
}

export function scoreCaptionForCue(cueId: BattleScoreCueId): string {
	switch (cueId) {
		case "death_clock_overture":
			return "Death Clock Overture (provisional GM render).";
		case "exploit_death_stinger":
			return "Exploit death stinger — confirmed terminal receipt only.";
		case "exploit_victory_stinger":
			return "Exploit victory stinger — Judge-backed success only.";
		case "next_battle_arena":
			return "Next arena cue — accepted arena transition only.";
		case "live_arena_loop":
			return "Live arena loop — battle lifecycle started.";
		default:
			return "";
	}
}
