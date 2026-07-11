/**
 * Battle score runtime catalog — provisional GM OGG v1.
 * MIDI sources remain under /battle-audio/score/midi for future synth replacement
 * without changing event bindings.
 */
import type { BattleRunnerSpriteId } from "../engine/battle-runner-sprites";
import { BATTLE_RUNNER_SPRITE_IDS } from "../engine/battle-runner-sprites";

export const BATTLE_MUSIC_RUNTIME_CATALOG_URL = "/battle-audio/score/v1/runtime-catalog.json";

export type BattleScoreCueId =
	| "death_clock_overture"
	| "exploit_death_stinger"
	| "exploit_victory_stinger"
	| "next_battle_arena"
	| "live_arena_loop";

export type BattleScoreCueSpec = {
	id: BattleScoreCueId;
	ogg: string;
	midi: string;
	loop: boolean;
	durationSeconds: number;
};

export type BattleSpriteMotifSpec = {
	spriteId: BattleRunnerSpriteId;
	ogg: string;
	midi: string;
};

/** Provisional GM / TimGM6mb renders — not final synth production. */
export const BATTLE_SCORE_PROVISIONAL_GM_RENDER = true as const;

export const BATTLE_SCORE_CUES: Record<BattleScoreCueId, BattleScoreCueSpec> = {
	death_clock_overture: {
		id: "death_clock_overture",
		ogg: "/battle-audio/score/v1/battle_intro_death_clock_overture.ogg",
		midi: "/battle-audio/score/midi/cues/battle_intro_death_clock_overture.mid",
		loop: false,
		durationSeconds: 46.9375,
	},
	exploit_death_stinger: {
		id: "exploit_death_stinger",
		ogg: "/battle-audio/score/v1/exploit_death_stinger.ogg",
		midi: "/battle-audio/score/midi/cues/exploit_death_stinger.mid",
		loop: false,
		durationSeconds: 2.82,
	},
	exploit_victory_stinger: {
		id: "exploit_victory_stinger",
		ogg: "/battle-audio/score/v1/exploit_victory_stinger.ogg",
		midi: "/battle-audio/score/midi/cues/exploit_victory_stinger.mid",
		loop: false,
		durationSeconds: 4.9138,
	},
	next_battle_arena: {
		id: "next_battle_arena",
		ogg: "/battle-audio/score/v1/next_battle_arena_level.ogg",
		midi: "/battle-audio/score/midi/cues/next_battle_arena_level.mid",
		loop: false,
		durationSeconds: 19.2857,
	},
	live_arena_loop: {
		id: "live_arena_loop",
		ogg: "/battle-audio/score/v1/battle_started_background_loop.ogg",
		midi: "/battle-audio/score/midi/cues/battle_started_background_loop.mid",
		loop: true,
		durationSeconds: 30,
	},
};

export const BATTLE_SPRITE_MOTIFS: Record<BattleRunnerSpriteId, BattleSpriteMotifSpec> = Object.fromEntries(
	BATTLE_RUNNER_SPRITE_IDS.map((spriteId) => [
		spriteId,
		{
			spriteId,
			ogg: `/battle-audio/score/v1/motifs/${spriteId}.ogg`,
			midi: `/battle-audio/score/midi/character_motifs/${spriteId}.mid`,
		},
	]),
) as Record<BattleRunnerSpriteId, BattleSpriteMotifSpec>;

/** Legacy Genesis-style MIDI — reference only; not a selectable production intro. */
export const BATTLE_LEGACY_GENESIS_INTRO_MIDI = "/battle-audio/legacy/battle-004-round-intro.mid";

export const BATTLE_SCORE_BINDINGS = {
	introTitle: "death_clock_overture",
	confirmedExploitTerminal: "exploit_death_stinger",
	confirmedExploitSuccess: "exploit_victory_stinger",
	acceptedArenaTransition: "next_battle_arena",
	battleLifecycleStarted: "live_arena_loop",
	actorFocusOrEntrance: "sprite_motif",
} as const;

export function isBattleScoreCueId(value: string): value is BattleScoreCueId {
	return value in BATTLE_SCORE_CUES;
}

export function motifSpecForSprite(spriteId: string | null | undefined): BattleSpriteMotifSpec | null {
	if (!spriteId) return null;
	return BATTLE_SPRITE_MOTIFS[spriteId as BattleRunnerSpriteId] ?? null;
}
