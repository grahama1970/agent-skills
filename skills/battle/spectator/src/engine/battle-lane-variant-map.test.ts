import { describe, expect, it } from "vitest";
import type { BattleSpriteThemeV1, Lane } from "../lib/battle-types";
import adaptiveLineageLive from "../lineage/__fixtures__/adaptive-lineage-live.json";
import {
	BATTLE_RUNNER_FLOOR_SPRITE_ID,
	ENABLED_RUNNER_SPRITE_IDS,
	spriteIdForLane,
	spriteThemeSpriteId,
	spriteVariantForLane,
} from "./battle-lane-variant-map";

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

/** Build a Lane carrying the receipt-backed identity of an adaptive-lineage node. */
type LineageNode = {
	id: string;
	generation: number;
	selected: boolean;
	runner_up: boolean;
	role: string;
};
function laneFromSpecimen(node: LineageNode): Lane {
	return lane({
		id: node.id,
		generation: node.generation,
		team: "red", // the accepted adaptive gate is the red exploit lineage
		selected: node.selected,
		runner_up: node.runner_up,
	});
}

const spriteTheme: BattleSpriteThemeV1 = {
	schema: "battle.sprite_theme.v1",
	variants: {
		heavy_red_alpha: { sprite_id: "crimson_hornbreaker" },
		plague_nurgling: { sprite_id: "plague_nurgling" },
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

describe("spriteIdForLane — adaptive-lineage four specimens", () => {
	const nodes = adaptiveLineageLive.nodes as LineageNode[];
	const specimens = ["G0", "G1-A", "G1-B", "G2"].map((id) => {
		const node = nodes.find((n) => n.id === id);
		if (!node) throw new Error(`fixture missing specimen ${id}`);
		return node;
	});

	it("resolves the four specimens to four DISTINCT sprite ids", () => {
		const ids = specimens.map((node) => spriteIdForLane(laneFromSpecimen(node)));
		expect(new Set(ids).size).toBe(4);
	});

	it("keeps plague_nurgling enabled and assigned to the G0 seed (mandatory floor)", () => {
		const g0 = specimens.find((n) => n.id === "G0")!;
		expect(spriteIdForLane(laneFromSpecimen(g0))).toBe("plague_nurgling");
		expect(ENABLED_RUNNER_SPRITE_IDS).toContain("plague_nurgling");
		expect(BATTLE_RUNNER_FLOOR_SPRITE_ID).toBe("plague_nurgling");
	});

	it("makes selected-G1 and runner-up-G1 visually distinguishable from each other and G0/G2", () => {
		const byId = Object.fromEntries(
			specimens.map((n) => [n.id, spriteIdForLane(laneFromSpecimen(n))]),
		);
		expect(byId["G1-A"]).not.toBe(byId["G1-B"]); // selected vs runner-up
		expect(byId["G1-A"]).not.toBe(byId["G0"]);
		expect(byId["G1-A"]).not.toBe(byId["G2"]);
		expect(byId["G1-B"]).not.toBe(byId["G2"]);
	});

	it("is deterministic — same specimen twice yields the same sprite", () => {
		for (const node of specimens) {
			const a = spriteIdForLane(laneFromSpecimen(node));
			const b = spriteIdForLane(laneFromSpecimen(node));
			expect(a).toBe(b);
		}
	});

	it("only ever resolves to validated, enabled sprite ids", () => {
		for (const node of specimens) {
			expect(ENABLED_RUNNER_SPRITE_IDS).toContain(spriteIdForLane(laneFromSpecimen(node)));
		}
	});

	it("never enables an atlas the sprite-reviewer rejected/flagged for revision", () => {
		// Locked in by the creator↔reviewer visual-acceptance loop.
		expect(ENABLED_RUNNER_SPRITE_IDS).not.toContain("crimson_hornbreaker"); // REJECT: garbled
		expect(ENABLED_RUNNER_SPRITE_IDS).not.toContain("skull_horn"); // REVISE: fragmented/redundant
		// and no lane ever resolves to one of them
		const teams = ["red", "blue"] as const;
		for (const team of teams)
			for (const generation of [0, 1, 2])
				for (const role of [{}, { selected: true }, { runner_up: true }]) {
					const id = spriteIdForLane(lane({ id: "probe", team, generation, ...role }));
					expect(id).not.toBe("crimson_hornbreaker");
					expect(id).not.toBe("skull_horn");
				}
	});
});

describe("spriteIdForLane — render fixture identity (team x generation)", () => {
	it("resolves the four render specimens (red/blue x gen1/gen2) to distinct sprites", () => {
		const ids = [
			spriteIdForLane(lane({ id: "red-1", team: "red", generation: 1 })),
			spriteIdForLane(lane({ id: "red-2", team: "red", generation: 2 })),
			spriteIdForLane(lane({ id: "blue-1", team: "blue", generation: 1 })),
			spriteIdForLane(lane({ id: "blue-2", team: "blue", generation: 2 })),
		];
		expect(new Set(ids).size).toBe(4);
		for (const id of ids) expect(ENABLED_RUNNER_SPRITE_IDS).toContain(id);
	});

	it("falls back to the floor sprite for unknown identities", () => {
		expect(spriteIdForLane(lane({ id: "x", team: "red", generation: 9 }))).toBe("plague_nurgling");
	});

	it("spriteVariantForLane remains a compatibility alias", () => {
		expect(spriteVariantForLane(lane({ id: "seed", team: "red", generation: 0 }))).toBe("plague_nurgling");
	});
});
