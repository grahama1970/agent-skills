import type { BattleSpriteThemeV1, Lane } from "../lib/battle-types";
import type { BattleRunnerSpriteId } from "./battle-runner-sprites";
import { BATTLE_RUNNER_SPRITE_IDS } from "./battle-runner-sprites";

const BATTLE_RUNNER_SPRITE_ID_SET = new Set<string>(BATTLE_RUNNER_SPRITE_IDS);

/** Design-fixture fallback only. Receipt-backed lanes should carry actor_visual.variant_id. */
const LANE_VARIANT_OVERRIDES: Record<string, BattleRunnerSpriteId> = {
	"payload-857": "crimson_chainsword_berserker",
	"payload-857-A": "crimson_chainsaw_demon",
	"payload-857-receipt": "crimson_hornbreaker",
	"payload-857-red-1": "plague_nurgling",
	"payload-231": "purple_horn_imp",
	"payload-404": "skull_horn",
	"payload-118": "blue_lizard",
	"payload-620": "typhus",
	"payload-912": "crimson_chainsword_berserker",
	"payload-912-A": "plague_nurgling",
	"payload-912-B": "crimson_hornbreaker",
	"payload-912-C": "purple_horn_imp",
	"payload-912-D": "crimson_chainsaw_demon",
};

function hashLaneId(laneId: string): number {
	let hash = 0;
	for (let index = 0; index < laneId.length; index += 1) {
		hash = (hash * 31 + laneId.charCodeAt(index)) >>> 0;
	}
	return hash;
}

function asRunnerSpriteId(spriteId: string | undefined): BattleRunnerSpriteId | null {
	if (spriteId && BATTLE_RUNNER_SPRITE_ID_SET.has(spriteId)) {
		return spriteId as BattleRunnerSpriteId;
	}
	return null;
}

function variantIdForLane(lane: Lane): string | null {
	return lane.actor_visual?.variant_id ?? null;
}

/** Resolve backend variant_id through fixture sprite_theme before loading Pixi spritesheets. */
export function spriteThemeSpriteId(variantId: string, spriteTheme?: BattleSpriteThemeV1): string {
	const themed = spriteTheme?.variants?.[variantId]?.sprite_id;
	return themed ?? variantId;
}

export function spriteIdForLane(lane: Lane, spriteTheme?: BattleSpriteThemeV1): BattleRunnerSpriteId {
	const actorVariantId = variantIdForLane(lane);
	if (actorVariantId) {
		const resolved = asRunnerSpriteId(spriteThemeSpriteId(actorVariantId, spriteTheme));
		if (resolved) return resolved;
	}

	const fallbackVariant = LANE_VARIANT_OVERRIDES[lane.id];
	if (fallbackVariant) {
		const resolved = asRunnerSpriteId(spriteThemeSpriteId(fallbackVariant, spriteTheme));
		if (resolved) return resolved;
	}

	const hashed = BATTLE_RUNNER_SPRITE_IDS[hashLaneId(lane.id) % BATTLE_RUNNER_SPRITE_IDS.length];
	return asRunnerSpriteId(spriteThemeSpriteId(hashed, spriteTheme)) ?? hashed;
}

/** @deprecated use spriteIdForLane */
export function spriteVariantForLane(lane: Lane, spriteTheme?: BattleSpriteThemeV1): BattleRunnerSpriteId {
	return spriteIdForLane(lane, spriteTheme);
}
