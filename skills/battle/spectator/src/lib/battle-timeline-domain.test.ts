import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { receiptBackedFixture } from "./battle-data";
import { battleTimelineDomain } from "./battle-timeline-domain";
import type { BattleNormalizedUxFixture } from "./battle-types";

const receiptReplayFixture = JSON.parse(
	readFileSync(
		resolve(import.meta.dirname, "../../../local/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json"),
		"utf8",
	),
) as BattleNormalizedUxFixture;

describe("battleTimelineDomain", () => {
	it("uses elapsed-axis playhead authority when model is active", () => {
		const domain = battleTimelineDomain(receiptBackedFixture, false);
		expect(domain.source).toBe("timeline_elapsed_axis");
		expect(domain.currentSeconds).toBeCloseTo(
			receiptBackedFixture.timeline_elapsed_axis_model?.playhead?.current_elapsed_seconds ?? 0,
			5,
		);
	});

	it("uses elapsed-axis playhead on parent-spawn replay fixture", () => {
		const domain = battleTimelineDomain(receiptReplayFixture, false);
		expect(domain.source).toBe("timeline_elapsed_axis");
		expect(domain.currentSeconds).toBeCloseTo(
			receiptReplayFixture.timeline_elapsed_axis_model?.playhead?.current_elapsed_seconds ?? 0,
			5,
		);
		expect(domain.currentSeconds).not.toBe(receiptReplayFixture.battle_clock?.elapsed_seconds);
	});
});
