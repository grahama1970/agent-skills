import { describe, expect, it } from "vitest";
import type { BattleSpriteThemeV1, Lane } from "../lib/battle-types";
import { spriteIdForLane, spriteThemeSpriteId, spriteVariantForLane } from "./battle-lane-variant-map";

function lane(partial: Partial<Lane> & Pick<Lane, "id">): Lane {
	return {
		name: partial.id,
		payloadId: partial.id,
		generation: 1,
		team: "red",
		xStart: 0,
		xEnd: 100,
		runnerX: 0,
		runnerState: "advance",
		lineColor: "red",
		terminal: "none",
		events: [],
		...partial,
	};
}

const spriteTheme: BattleSpriteThemeV1 = {
	schema: "battle.sprite_theme.v1",
	variants: {
		heavy_red_alpha: {
			sprite_id: "crimson_hornbreaker",
		},
		plague_nurgling: {
			sprite_id: "plague_nurgling",
		},
	},
};

describe("spriteThemeSpriteId", () => {
	it("maps variant_id to sprite_theme sprite_id when they diverge", () => {
		expect(spriteThemeSpriteId("heavy_red_alpha", spriteTheme)).toBe("crimson_hornbreaker");
	});

	it("falls back to variant_id when theme entry is missing", () => {
		expect(spriteThemeSpriteId("plague_nurgling", spriteTheme)).toBe("plague_nurgling");
	});
});

describe("spriteIdForLane", () => {
	it("uses plague_nurgling even when backend metadata requests another variant", () => {
		expect(
			spriteIdForLane(
				lane({
					id: "payload-857-receipt",
					actor_visual: {
						schema: "battle.actor_visual.v1",
						actor_id: "payload-857-receipt",
						lane_id: "payload-857-receipt",
						role: "red_exploit",
						team: "red",
						archetype: "chaos_marine_heavy",
						variant_id: "heavy_red_alpha",
					},
				}),
				spriteTheme,
			),
		).toBe("plague_nurgling");
	});

	it("uses plague_nurgling when backend metadata already requests it", () => {
		expect(
			spriteIdForLane(
				lane({
					id: "payload-857-receipt",
					actor_visual: {
						schema: "battle.actor_visual.v1",
						actor_id: "payload-857-receipt",
						lane_id: "payload-857-receipt",
						role: "red_exploit",
						team: "red",
						archetype: "chaos_marine_heavy",
						variant_id: "plague_nurgling",
					},
				}),
			),
		).toBe("plague_nurgling");
	});

	it("uses plague_nurgling for lanes without actor metadata", () => {
		expect(spriteIdForLane(lane({ id: "payload-857-receipt" }))).toBe("plague_nurgling");
	});

	it("spriteVariantForLane remains a compatibility alias", () => {
		expect(spriteVariantForLane(lane({ id: "payload-857-receipt" }))).toBe("plague_nurgling");
	});
});
