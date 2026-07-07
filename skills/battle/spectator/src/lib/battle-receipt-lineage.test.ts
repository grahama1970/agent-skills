import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { generatedBattleFixture } from "./battle-data.generated";
import type { BattleNormalizedUxFixture, Lane } from "./battle-types";
import { childSpawnElapsedSeconds, lanesVisibleAtPlayhead, spawnTimingFieldsConsistent } from "./battle-receipt-replay";

const legacyFixture = generatedBattleFixture as unknown as BattleNormalizedUxFixture;
const legacyLanes = legacyFixture.lanes as Lane[];

const receiptReplayFixture = JSON.parse(
	readFileSync(
		resolve(import.meta.dirname, "../../../local/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json"),
		"utf8",
	),
) as BattleNormalizedUxFixture;
const receiptLanes = receiptReplayFixture.lanes as Lane[];

describe("battle receipt lineage", () => {
	it("reads spawn time for payload-857-red-1", () => {
		expect(childSpawnElapsedSeconds(legacyFixture, "payload-857-red-1")).toBeCloseTo(83.585509, 3);
	});

	it("hides child lane before spawn", () => {
		const before = lanesVisibleAtPlayhead(legacyLanes, legacyFixture, 80);
		expect(before.map((lane) => lane.id)).toEqual(["payload-857-receipt"]);
	});

	it("shows child lane after spawn", () => {
		const after = lanesVisibleAtPlayhead(legacyLanes, legacyFixture, 90);
		expect(after.map((lane) => lane.id)).toEqual(["payload-857-receipt", "payload-857-red-1"]);
	});

	it("accepts split visibility vs first-active-segment timing on replay fixture", () => {
		expect(spawnTimingFieldsConsistent(receiptReplayFixture, "payload-857-red-1")).toBe(true);
		expect(childSpawnElapsedSeconds(receiptReplayFixture, "payload-857-red-1")).toBeCloseTo(83.585509, 3);
		expect(lanesVisibleAtPlayhead(receiptLanes, receiptReplayFixture, 90).map((lane) => lane.id)).toEqual([
			"payload-857-receipt",
			"payload-857-red-1",
		]);
	});
});
