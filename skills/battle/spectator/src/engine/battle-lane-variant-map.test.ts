import { describe, expect, it } from "vitest";
import type { Lane } from "../lib/battle-types";
import { spriteVariantForLane } from "./battle-lane-variant-map";

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

describe("spriteVariantForLane", () => {
	it("prefers backend actor_visual variant over design fallback lane map", () => {
		expect(
			spriteVariantForLane(
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

	it("keeps the design fallback for lanes without backend actor_visual", () => {
		expect(spriteVariantForLane(lane({ id: "payload-857-receipt" }))).toBe("crimson_hornbreaker");
	});
});
