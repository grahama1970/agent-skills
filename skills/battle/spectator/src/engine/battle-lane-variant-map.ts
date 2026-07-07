import type { Lane } from "../lib/battle-types";
import type { BattleRunnerSpriteId } from "./battle-runner-sprites";
import { BATTLE_RUNNER_SPRITE_IDS } from "./battle-runner-sprites";

/** UX-owned lane → runtime sprite mapping. Backend must not hardcode asset paths. */
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

export function spriteVariantForLane(lane: Lane): BattleRunnerSpriteId {
	return LANE_VARIANT_OVERRIDES[lane.id] ?? BATTLE_RUNNER_SPRITE_IDS[hashLaneId(lane.id) % BATTLE_RUNNER_SPRITE_IDS.length];
}
