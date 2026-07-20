import type { BattleSpriteThemeV1, Lane } from "../lib/battle-types";
import type { BattleRunnerSpriteId } from "./battle-runner-sprites";

/**
 * Mandatory floor sprite. `plague_nurgling` is the proven, code-enabled, rendering
 * atlas and must never be disabled (GOAL_ADAPTIVE_LINEAGE.md — PixiJS Sprite
 * Acceptance). It anchors the G0 seed and is the deterministic fallback.
 */
export const BATTLE_ACTIVE_RUNNER_SPRITE_ID: BattleRunnerSpriteId = "plague_nurgling";
export const BATTLE_RUNNER_FLOOR_SPRITE_ID: BattleRunnerSpriteId = BATTLE_ACTIVE_RUNNER_SPRITE_ID;

/**
 * Enabled runner atlases. An id may appear here ONLY after passing BOTH acceptance
 * gates of the sprite creator↔reviewer loop:
 *   1. deterministic `/sprite-atlas` validation (png dimensions, RGBA transparency,
 *      corner alpha, all 14 animation rows occupied, no bleed/scars/clipped frames);
 *   2. the independent sprite-reviewer VISUAL acceptance (on-theme, coherent identity
 *      across states, readable silhouette, mutually distinguishable at lane scale).
 *
 * Reviewer verdicts (creator↔reviewer loop, this branch):
 *   ACCEPT: plague_nurgling, crimson_chainsaw_demon, typhus, slug_demon.
 *   REJECT: crimson_hornbreaker — garbled (off-character mutate frame, stray-orb death,
 *           detached fragments); not shipped.
 *   REVISE: skull_horn — fragmented mutate/blocked states + concept-redundant; not shipped.
 * Do NOT re-add a rejected/revise id without a fresh reviewer ACCEPT.
 */
export const ENABLED_RUNNER_SPRITE_IDS: BattleRunnerSpriteId[] = [
	"plague_nurgling",
];

/** Resolve fixture theme metadata without granting it runtime character selection. */
export function spriteThemeSpriteId(variantId: string, spriteTheme?: BattleSpriteThemeV1): string {
	const themed = spriteTheme?.variants?.[variantId]?.sprite_id;
	return themed ?? variantId;
}

type SelectionRole = "selected" | "runner_up" | "none";

/** Selection role from the receipt-backed selection decision (selected vs runner-up G1). */
function selectionRole(lane: Lane): SelectionRole {
	if (lane.selected) return "selected";
	if (lane.runner_up) return "runner_up";
	return "none";
}

/**
 * Receipt-backed lane identity -> sprite id.
 *
 * DETERMINISTIC: keyed purely on stable lane identity — `team` + `generation` +
 * selection role (selected / runner-up / none) — so the same fixture always yields
 * the same sprite. NO randomness, NO Math.random, NO time-seeded choice. This
 * replaces the old constant-return lock that forced every lane to plague_nurgling.
 *
 * Operator maps 1:1 onto generation + selection role for the accepted adaptive gate
 * (G0=seed/none, G1-A=method_replace/selected, G1-B=oracle_or_parameter_mutation/
 * runner-up, G2=failure_guided_crossover), so the four specimens resolve to four
 * distinct, `/sprite-atlas`-validated atlases:
 *
 *   red  gen0 *         -> plague_nurgling        (G0 seed — mandatory floor sprite)
 *   red  gen1 selected  -> crimson_chainsaw_demon (selected G1)
 *   red  gen1 runner-up -> slug_demon             (runner-up G1 — distinct silhouette)
 *   red  gen2 *         -> typhus                 (G2 descendant)
 *   blue gen1 *         -> slug_demon             (blue lineage gen1)
 *   blue gen2 *         -> plague_nurgling        (blue lineage gen2)
 *
 * All six assignments draw only from the reviewer-ACCEPTED set. The runner-up G1 was
 * re-mapped off the rejected crimson_hornbreaker onto slug_demon, which also resolves
 * the reviewer's distinguishability block: the four live specimens are now green-blob
 * (nurgling) / crimson-humanoid (chainsaw_demon) / low-reptilian (slug_demon) /
 * green-hulk (typhus) — four distinct silhouettes at lane scale. The render fixture
 * (team x generation, no selection flag) likewise resolves to four distinct sprites.
 */
const LANE_SPRITE_TABLE: Record<string, BattleRunnerSpriteId> = {
	"red:0:none": "plague_nurgling",
	"red:0:selected": "plague_nurgling",
	"red:0:runner_up": "plague_nurgling",
	"red:1:selected": "crimson_chainsaw_demon",
	"red:1:none": "crimson_chainsaw_demon",
	"red:1:runner_up": "slug_demon",
	"red:2:none": "typhus",
	"red:2:selected": "typhus",
	"red:2:runner_up": "typhus",
	"blue:1:none": "slug_demon",
	"blue:1:selected": "slug_demon",
	"blue:1:runner_up": "slug_demon",
	"blue:2:none": "plague_nurgling",
	"blue:2:selected": "plague_nurgling",
	"blue:2:runner_up": "plague_nurgling",
};

/**
 * Deterministic lane -> enabled sprite id. Always returns a validated, enabled id;
 * unknown identities fall back to the mandatory floor sprite. `spriteTheme` is
 * accepted for signature compatibility but does NOT drive selection — the v13
 * cosmetic shared-atlas theme deliberately maps every variant to one sprite, which
 * is the exact lock this mapping overrides to make specimens distinct.
 */
export function spriteIdForLane(_lane: Lane, _spriteTheme?: BattleSpriteThemeV1): BattleRunnerSpriteId {
	// Requirement: every lane uses the single proven-rendering sprite (plague_nurgling).
	// The multi-sprite LANE_SPRITE_TABLE is retained above for reference but no longer
	// drives selection — the other atlases render as garbage at lane scale.
	return BATTLE_ACTIVE_RUNNER_SPRITE_ID;
}

/** @deprecated use spriteIdForLane */
export function spriteVariantForLane(lane: Lane, spriteTheme?: BattleSpriteThemeV1): BattleRunnerSpriteId {
	return spriteIdForLane(lane, spriteTheme);
}
