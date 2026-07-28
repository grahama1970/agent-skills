import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { battleLanesForView } from "./battle-data";
import {
	collectReceiptBeats,
	heroReceiptBeats,
	nextReceiptBeat,
	receiptBeatsForTicker,
} from "./battle-receipt-beats";

describe("collectReceiptBeats", () => {
	it("builds handoff spawn beat and block_impact on parent-spawn fixture", async () => {
		const fixture = JSON.parse(
			await readFile(
				resolve(import.meta.dirname, "../../public/battle-fixtures/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json"),
				"utf8",
			),
		);
		const lanes = battleLanesForView(fixture.lanes, fixture);
		const beats = collectReceiptBeats(fixture, lanes);
		const handoff = beats.find((beat) => beat.kind === "spawn");
		const blockImpact = beats.find((beat) => beat.kind === "block_impact");
		expect(handoff?.pixi.emphasis).toBe("spawn");
		expect(blockImpact?.pixi.emphasis).toBe("block_impact");
		expect(blockImpact?.react.deathCard).toBe(false);
	});

	it("next hero beat advances highlight reel", async () => {
		const fixture = JSON.parse(
			await readFile(
				resolve(import.meta.dirname, "../../public/battle-fixtures/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json"),
				"utf8",
			),
		);
		const lanes = battleLanesForView(fixture.lanes, fixture);
		const heroes = heroReceiptBeats(collectReceiptBeats(fixture, lanes));
		const next = nextReceiptBeat(heroes, 0);
		expect(next?.kind).toBe("spawn");
	});
});


describe("receiptBeatsForTicker", () => {
	it("suppresses stale survival highlights after a confirmed kill on the same lane", () => {
		const fixture = {
			battle_id: "battle-004",
			proof_mode: "receipt_backed_fixture",
			clock: { allotted_seconds: 1200, current_elapsed_seconds: 100 },
			battle_clock: { allotted_seconds: 1200 },
			timeline_elapsed_axis_model: { x_position_is_elapsed_time: true },
			lanes: [
				{
					id: "payload-857-red-1",
					name: "Archive Escape red-1",
					payloadId: "payload-857-red-1",
					generation: 2,
					xStart: 40,
					xEnd: 90,
					events: [
						{ id: "blast", kind: "blue_blast", x: 80, elapsed_seconds: 90, proven: true },
						{ id: "killed", kind: "killed", x: 85, elapsed_seconds: 95, proven: true },
					],
				},
			],
		} as any;
		const beats = collectReceiptBeats(fixture, fixture.lanes);
		const ticker = receiptBeatsForTicker(beats, 99, 5);
		const highlights = ticker.map((beat) => beat.react.liveEvent.highlight);
		expect(highlights.some((item) => item.includes("ELIMINATED") || item.includes("SURVIVES"))).toBe(true);
		expect(highlights.filter((item) => item.includes("SURVIVES"))).toHaveLength(0);
	});
});
