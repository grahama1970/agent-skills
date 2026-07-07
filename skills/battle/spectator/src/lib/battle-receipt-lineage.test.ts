import { describe, expect, it } from "vitest";
import { generatedBattleFixture } from "./battle-data.generated";
import type { BattleNormalizedUxFixture, Lane } from "./battle-types";
import { childSpawnElapsedSeconds, lanesVisibleAtPlayhead } from "./battle-receipt-replay";

const fixture = generatedBattleFixture as unknown as BattleNormalizedUxFixture;
const lanes = fixture.lanes as Lane[];

describe("battle receipt lineage", () => {
	it("reads spawn time for payload-857-red-1", () => {
		expect(childSpawnElapsedSeconds(fixture, "payload-857-red-1")).toBeCloseTo(116.973449, 3);
	});

	it("hides child lane before spawn", () => {
		const before = lanesVisibleAtPlayhead(lanes, fixture, 100);
		expect(before.map((lane) => lane.id)).toEqual(["payload-857-receipt"]);
	});

	it("shows child lane after spawn", () => {
		const after = lanesVisibleAtPlayhead(lanes, fixture, 120);
		expect(after.map((lane) => lane.id)).toEqual(["payload-857-receipt", "payload-857-red-1"]);
	});
});
