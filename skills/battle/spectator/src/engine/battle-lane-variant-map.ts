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
 * Enabled runner atlases. Every id here passes deterministic `/sprite-atlas`
 * validation against profile `battle-pixijs-runtime-64-v1` (png dimensions, RGBA
 * transparency, corner alpha, all 14 animation rows fully occupied, no unused-cell
 * bleed, no grid scars, no clipped required frames, manifest animation arrays +
 * frame rectangles). Do NOT add an id here until its atlas PASSES that gate.
 */
export const ENABLED_RUNNER_SPRITE_IDS: BattleRunnerSpriteId[] = [
	"plague_nurgling",
	"crimson_chainsaw_demon",
	"crimson_hornbreaker",
	"typhus",
	"slug_demon",
	"skull_horn",
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
 *   red  gen0 none      -> plague_nurgling        (G0 seed — mandatory floor sprite)
 *   red  gen1 selected  -> crimson_chainsaw_demon (selected G1)
 *   red  gen1 runner-up -> crimson_hornbreaker    (runner-up G1 — distinct from selected)
 *   red  gen2 *         -> typhus                 (G2 descendant)
 *   blue gen1 *         -> slug_demon             (blue lineage gen1)
 *   blue gen2 *         -> skull_horn             (blue lineage gen2)
 *
 * The render fixture encodes the four specimens as team(red/blue) x generation(1/2)
 * with no selection flag; the table above keeps those four distinct too.
 */
const LANE_SPRITE_TABLE: Record<string, BattleRunnerSpriteId> = {
	"red:0:none": "plague_nurgling",
	"red:0:selected": "plague_nurgling",
	"red:0:runner_up": "plague_nurgling",
	"red:1:selected": "crimson_chainsaw_demon",
	"red:1:none": "crimson_chainsaw_demon",
	"red:1:runner_up": "crimson_hornbreaker",
	"red:2:none": "typhus",
	"red:2:selected": "typhus",
	"red:2:runner_up": "typhus",
	"blue:1:none": "slug_demon",
	"blue:1:selected": "slug_demon",
	"blue:1:runner_up": "slug_demon",
	"blue:2:none": "skull_horn",
	"blue:2:selected": "skull_horn",
	"blue:2:runner_up": "skull_horn",
};

/**
 * Deterministic lane -> enabled sprite id. Always returns a validated, enabled id;
 * unknown identities fall back to the mandatory floor sprite. `spriteTheme` is
 * accepted for signature compatibility but does NOT drive selection — the v13
 * cosmetic shared-atlas theme deliberately maps every variant to one sprite, which
 * is the exact lock this mapping overrides to make specimens distinct.
 */
export function spriteIdForLane(lane: Lane, _spriteTheme?: BattleSpriteThemeV1): BattleRunnerSpriteId {
	const key = `${lane.team}:${lane.generation}:${selectionRole(lane)}`;
	const mapped = LANE_SPRITE_TABLE[key];
	if (mapped) return mapped;
	const genFallback = LANE_SPRITE_TABLE[`${lane.team}:${lane.generation}:none`];
	return genFallback ?? BATTLE_RUNNER_FLOOR_SPRITE_ID;
}

/** @deprecated use spriteIdForLane */
export function spriteVariantForLane(lane: Lane, spriteTheme?: BattleSpriteThemeV1): BattleRunnerSpriteId {
	return spriteIdForLane(lane, spriteTheme);
}
