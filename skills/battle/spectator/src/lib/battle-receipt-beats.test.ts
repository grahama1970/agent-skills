import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { battleLanesForView } from "./battle-data";
import {
	collectReceiptBeatCrossings,
	collectReceiptBeats,
	heroReceiptBeats,
	highlightReelDwellMs,
	nextReceiptBeat,
} from "./battle-receipt-beats";
import { KILL_SHOT_TRAVEL_SECONDS } from "../engine/battle-pixi-kill-shot";

describe("collectReceiptBeats", () => {
	it("builds kill_impact hero beat on kill-shot fixture", async () => {
		const fixture = JSON.parse(
			await readFile(
				resolve(import.meta.dirname, "../../public/battle-fixtures/battle-004-kill-shot-pixi-replay/battle.normalized_ux_fixture.json"),
				"utf8",
			),
		);
		const lanes = battleLanesForView(fixture.lanes, fixture);
		const beats = collectReceiptBeats(fixture, lanes);
		const killImpact = beats.find((beat) => beat.kind === "kill_impact");
		expect(killImpact).toBeTruthy();
		expect(killImpact?.react.deathCard).toBe(true);
		expect(killImpact?.camera.follow).toBe(true);
		expect(killImpact?.pixi.emphasis).toBe("kill_impact");
	});

	it("crosses director beats forward across playhead", async () => {
		const fixture = JSON.parse(
			await readFile(
				resolve(import.meta.dirname, "../../public/battle-fixtures/battle-004-kill-shot-pixi-replay/battle.normalized_ux_fixture.json"),
				"utf8",
			),
		);
		const lanes = battleLanesForView(fixture.lanes, fixture);
		const beats = collectReceiptBeats(fixture, lanes);
		const childLane = lanes.find((lane) => lane.id === "payload-857-red-1")!;
		const blastAt = childLane.events.find((e) => e.kind === "blue_blast")!.elapsed_seconds!;
		const crossed = collectReceiptBeatCrossings({
			prevSeconds: blastAt - 1,
			nextSeconds: blastAt + KILL_SHOT_TRAVEL_SECONDS + 0.1,
			beats,
		});
		expect(crossed.some((beat) => beat.kind === "kill_impact")).toBe(true);
	});

	it("tunes camera pre/post-roll per beat kind", async () => {
		const fixture = JSON.parse(
			await readFile(
				resolve(import.meta.dirname, "../../public/battle-fixtures/battle-004-kill-shot-pixi-replay/battle.normalized_ux_fixture.json"),
				"utf8",
			),
		);
		const lanes = battleLanesForView(fixture.lanes, fixture);
		const beats = collectReceiptBeats(fixture, lanes);
		const killImpact = beats.find((beat) => beat.kind === "kill_impact")!;
		const handoff = beats.find((beat) => beat.kind === "spawn")!;
		expect(highlightReelDwellMs(killImpact)).toBe(2380);
		expect(highlightReelDwellMs(handoff)).toBe(1760);
	});

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
				resolve(import.meta.dirname, "../../public/battle-fixtures/battle-004-kill-shot-pixi-replay/battle.normalized_ux_fixture.json"),
				"utf8",
			),
		);
		const lanes = battleLanesForView(fixture.lanes, fixture);
		const heroes = heroReceiptBeats(collectReceiptBeats(fixture, lanes));
		const next = nextReceiptBeat(heroes, 0);
		expect(next?.kind).toBe("spawn");
	});
});
