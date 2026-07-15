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

async function memoryFixture() {
	return JSON.parse(
		await readFile(
			resolve(import.meta.dirname, "../../public/battle-fixtures/battle-004-adaptive-memory-v14/battle.normalized_ux_fixture.json"),
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

describe("Battle V14 adaptive memory projection", () => {
	it("validates and projects the receipt-backed G2/G3 memory continuation", async () => {
		const validated = validateAdaptiveLineageFixture(await memoryFixture());
		expect(validated.ok).toBe(true);
		if (!validated.ok) return;
		expect(validated.fixture.events).toHaveLength(9);
		expect(validated.fixture.lanes.map((lane) => lane.lane_id)).toEqual(["red-g2", "red-g3", "blue-g2", "blue-g3"]);
		expect(validated.fixture.lineage_edges.every((edge) => edge.edge_kind === "memory_continuation")).toBe(true);

		const fixture = adaptiveLineageToRaceFixture(validated.fixture);
		expect(fixture.lanes.map((lane) => lane.id)).toEqual(["red-g2", "red-g3", "blue-g2", "blue-g3"]);
		expect(fixture.events).toHaveLength(9);
		expect(fixture.lanes.every((lane) => lane.terminal === "none")).toBe(true);
		expect(fixture.claims?.does_not_prove).toContain("memory improved either team");
		const evaluation = fixture.events.find((event) => String(event.event_type) === "memory_generation_evaluated");
		expect(evaluation?.claim_boundary?.does_not_prove).toContain("memory improved either team");
	});

	it("keeps memory children pending until provider use is acknowledged", async () => {
		const validated = validateAdaptiveLineageFixture(await memoryFixture());
		if (!validated.ok) throw new Error(validated.error.detail);
		const fixture = adaptiveLineageToRaceFixture(validated.fixture);
		const child = fixture.lanes.find((lane) => lane.id === "red-g3")!;
		expect(child.visible_from_elapsed_seconds).toBe(0);
		expect(child.first_active_segment_elapsed_seconds).toBe(64);
		expect(child.activitySegments?.[0]?.label).toBe("MEMORY PROMOTED · PENDING");
		expect(child.activitySegments?.[1]?.label).toBe("MEMORY USE ACKNOWLEDGED");
		expect(child.memory_promotion).toMatchObject({
			present: true,
			durable_promoted: true,
			reason: "provider use acknowledged",
		});
		const parent = fixture.lanes.find((lane) => lane.id === "red-g2")!;
		expect(parent.memory_promotion).toMatchObject({
			present: true,
			durable_promoted: true,
			reason: "selected evidence promoted to durable team memory",
		});
		const ticker = receiptBeatsVisibleAtPlayhead(collectReceiptBeats(fixture, fixture.lanes), 64.001, 2);
		expect(ticker.map((beat) => beat.react.liveEvent.notification)).toEqual([
			"Adaptive memory — RED G3 MEMORY CHILD: MEMORY USE ACKNOWLEDGED",
			"Adaptive memory — BLUE G3 MEMORY CHILD: MEMORY USE ACKNOWLEDGED",
		]);
		expect(ticker.every((beat) => !beat.react.liveEvent.notification.includes("Blue patch inbound"))).toBe(true);
	});

	it("fails closed when V14 memory use is presented as improvement", async () => {
		const source = await memoryFixture();
		source.renderer_contract.memory_use_is_not_improvement = false;
		const result = validateAdaptiveLineageFixture(source);
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.error.detail).toMatch(/claim gates/i);
	});
});
