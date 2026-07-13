import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { generatedBattleFixture } from "./battle-data.generated";
import type { BattleNormalizedUxFixture, Lane } from "./battle-types";
import {
	battleReceiptReplayFixtureKey,
	battleReceiptReplayFixtureUrl,
	childSpawnElapsedSeconds,
	lanesVisibleAtPlayhead,
	spawnTimingFieldsConsistent,
} from "./battle-receipt-replay";

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

	it("resolves committed receipt replay fixture keys from the route hash", () => {
		expect(battleReceiptReplayFixtureKey("#battle/receipt?engine=pixi")).toBe("battle-004-adaptive-lineage-v13");
		expect(battleReceiptReplayFixtureKey("#battle/receipt?engine=pixi&fixture=missing")).toBe("battle-004-adaptive-lineage-v13");
		expect(battleReceiptReplayFixtureUrl("#battle/receipt?engine=pixi&fixture=battle-005-ssrf-metadata")).toBe(
			"/battle-fixtures/battle-005-ssrf-metadata-pixi-replay/battle.normalized_ux_fixture.json",
		);
		expect(battleReceiptReplayFixtureUrl("#battle/receipt?engine=pixi&fixture=battle-006-pickle-deserialization")).toBe(
			"/battle-fixtures/battle-006-pickle-deserialization-pixi-replay/battle.normalized_ux_fixture.json",
		);
		expect(battleReceiptReplayFixtureUrl("#battle/receipt?engine=pixi&fixture=battle-007-file-upload")).toBe(
			"/battle-fixtures/battle-007-file-upload-pixi-replay/battle.normalized_ux_fixture.json",
		);
		expect(battleReceiptReplayFixtureKey("#battle/receipt?engine=pixi&fixture=battle-004-adaptive-lineage-v13")).toBe(
			"battle-004-adaptive-lineage-v13",
		);
	});
});
