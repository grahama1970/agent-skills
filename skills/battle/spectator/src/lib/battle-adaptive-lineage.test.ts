import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { runnerAnimationForLane } from "../engine/battle-runner-animation";
import { lineageTransitionPhase } from "../engine/battle-pixi-lineage";
import { adaptiveLineageToRaceFixture } from "./battle-adaptive-lineage-view-model";
import { validateAdaptiveLineageFixture } from "./battle-adaptive-lineage-validator";
import { collectReceiptBeats, receiptBeatsVisibleAtPlayhead } from "./battle-receipt-beats";
import { lanesVisibleAtPlayhead } from "./battle-receipt-replay";

async function sourceFixture() {
	return JSON.parse(
		await readFile(
			resolve(import.meta.dirname, "../../public/battle-fixtures/battle-004-adaptive-lineage-v13/battle.normalized_ux_fixture.json"),
			"utf8",
		),
	);
}

describe("Battle V13 adaptive lineage projection", () => {
	it("validates the four-lane causal contract and explicit shared atlas", async () => {
		const result = validateAdaptiveLineageFixture(await sourceFixture());
		expect(result.ok).toBe(true);
		if (!result.ok) return;
		expect(result.fixture.events).toHaveLength(24);
		expect(result.fixture.lanes.map((lane) => lane.lane_id)).toEqual(["red-g1", "red-g2", "blue-g1", "blue-g2"]);
		expect(result.fixture.lineage_edges).toHaveLength(2);
		expect(result.fixture.sprite_theme.variants["v13-shared-runner"].sprite_id).toBe("plague_nurgling");
		expect(result.fixture.events.filter((event) => event.event_type === "judge_verdict")).toHaveLength(2);
		expect(result.fixture.events.filter((event) => event.event_type === "judge_verdict").every((event) => event.scope === "generation_pair" && event.lane_id === null)).toBe(true);
	});

	it("keeps children hidden, pending, then active from the exact V13 receipts", async () => {
		const validated = validateAdaptiveLineageFixture(await sourceFixture());
		if (!validated.ok) throw new Error(validated.error.detail);
		const fixture = adaptiveLineageToRaceFixture(validated.fixture);
		expect(lanesVisibleAtPlayhead(fixture.lanes, fixture, 71.67).map((lane) => lane.id)).toEqual(["red-g1", "blue-g1"]);
		expect(lanesVisibleAtPlayhead(fixture.lanes, fixture, 71.68).map((lane) => lane.id)).toEqual(["red-g1", "red-g2", "blue-g1", "blue-g2"]);
		const child = fixture.lanes.find((lane) => lane.id === "red-g2")!;
		const allotted = fixture.battle_clock!.allotted_seconds!;
		expect(runnerAnimationForLane(child, 72, allotted, true)).toBe("idle");
		expect(lineageTransitionPhase(child, 72)).toBe("authorized_pending");
		expect(runnerAnimationForLane(child, 79.2, allotted, true)).toBe("spawn");
		expect(lineageTransitionPhase(child, 79.2)).toBe("descending");
		expect(runnerAnimationForLane(child, 82, allotted, true)).toBe("research");
		expect(lineageTransitionPhase(child, 82)).toBe("active");
		expect(runnerAnimationForLane(child, 134.45, allotted, true)).toBe("mutate");
		const ticker = receiptBeatsVisibleAtPlayhead(collectReceiptBeats(fixture, fixture.lanes), 134.451, 2);
		expect(ticker.map((beat) => beat.react.liveEvent.notification)).toEqual([
			"Adaptive lineage — RED G2 CHILD: MUTATION EVIDENCE VERIFIED",
			"Adaptive lineage — BLUE G2 CHILD: MUTATION EVIDENCE VERIFIED",
		]);
	});

	it("does not convert Judge, selection, or NO_PROMOTION into lane terminal truth", async () => {
		const validated = validateAdaptiveLineageFixture(await sourceFixture());
		if (!validated.ok) throw new Error(validated.error.detail);
		const fixture = adaptiveLineageToRaceFixture(validated.fixture);
		expect(fixture.lanes.every((lane) => lane.terminal === "none")).toBe(true);
		expect(fixture.lanes.flatMap((lane) => lane.events).some((event) => ["killed", "blocked", "promoted"].includes(event.kind))).toBe(false);
		const selection = fixture.events.find((event) => String(event.event_type) === "selection_decision");
		expect(selection?.claim_boundary?.does_not_prove).toContain("victory");
		expect(JSON.stringify(fixture)).not.toMatch(/\/tmp\/|tau-live|provider-workspace|arena\/private/);
	});

	it("fails closed when the shared sprite binding becomes semantic", async () => {
		const source = await sourceFixture();
		source.sprite_theme.semantic_authority = true;
		const result = validateAdaptiveLineageFixture(source);
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.error.detail).toMatch(/plague_nurgling theme/i);
	});
});
