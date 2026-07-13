import type { BattleSpriteThemeV1, Lane } from "../lib/battle-types";
import type { BattleRunnerSpriteId } from "./battle-runner-sprites";

/** The only runner atlas enabled until additional atlases pass visual acceptance. */
export const BATTLE_ACTIVE_RUNNER_SPRITE_ID: BattleRunnerSpriteId = "plague_nurgling";

/** Resolve fixture theme metadata without granting it runtime character selection. */
export function spriteThemeSpriteId(variantId: string, spriteTheme?: BattleSpriteThemeV1): string {
	const themed = spriteTheme?.variants?.[variantId]?.sprite_id;
	return themed ?? variantId;
}

/** Use one validated runner atlas for every lane. Lane identity remains UI metadata. */
export function spriteIdForLane(_lane: Lane, _spriteTheme?: BattleSpriteThemeV1): BattleRunnerSpriteId {
	return BATTLE_ACTIVE_RUNNER_SPRITE_ID;
}

/** @deprecated use spriteIdForLane */
export function spriteVariantForLane(lane: Lane, spriteTheme?: BattleSpriteThemeV1): BattleRunnerSpriteId {
	return spriteIdForLane(lane, spriteTheme);
}
