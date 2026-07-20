import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { runnerAnimationForLane } from "../engine/battle-runner-animation";
import { lineageTransitionPhase } from "../engine/battle-pixi-lineage";
import { adaptiveLineageToRaceFixture, applyAdaptiveMechanicsToRaceFixture } from "./battle-adaptive-lineage-view-model";
import { validateAdaptiveLineageFixture } from "./battle-adaptive-lineage-validator";
import { collectReceiptBeats, receiptBeatsVisibleAtPlayhead } from "./battle-receipt-beats";
import { lanesVisibleAtPlayhead } from "./battle-receipt-replay";
import type { BattleAdaptiveLineageMechanicsFixtureV1 } from "./battle-types";

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

async function liveMechanicsFixture(): Promise<BattleAdaptiveLineageMechanicsFixtureV1> {
	return JSON.parse(
		await readFile(
			resolve(import.meta.dirname, "../../public/battle-fixtures/battle-004-adaptive-lineage-live/adaptive-lineage-mechanics-fixture.json"),
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

	it("projects colocated live mechanics into G0/G1-A/G1-B/G2 race identities", async () => {
		const validated = validateAdaptiveLineageFixture(await sourceFixture());
		if (!validated.ok) throw new Error(validated.error.detail);
		const base = adaptiveLineageToRaceFixture(validated.fixture);
		const mechanics = await liveMechanicsFixture();
		const fixture = applyAdaptiveMechanicsToRaceFixture(base, mechanics);

		expect(mechanics.run_id).toBe("arena-adaptive-lineage-20260720T144034Z");
		expect(mechanics.nodes.find((node) => node.id === "G2")?.novelty_distance).toBe(4);
		expect(mechanics.nodes.find((node) => node.id === "G1-A")?.judge_outcome?.duration_seconds).toBe(1.195406);
		expect(mechanics.nodes.find((node) => node.id === "G1-B")?.judge_outcome?.duration_seconds).toBe(1.260919);
		expect(mechanics.nodes.find((node) => node.id === "G2")?.judge_outcome?.duration_seconds).toBe(1.285213);
		expect(mechanics.nodes.map((node) => [node.id, node.exploit_short_name])).toEqual([
			["G0", "Seed Slip"],
			["G1-A", "Module Slip"],
			["G1-B", "Arc Courier"],
			["G2", "ZipInfo Path"],
		]);

		expect(fixture.lanes.map((lane) => lane.id)).toEqual(["G0", "G1-A", "G1-B", "G2"]);
		expect(fixture.lanes.map((lane) => lane.name)).toEqual([
			"G0 Seed Slip",
			"G1-A Module Slip",
			"G1-B Arc Courier",
			"G2 ZipInfo Path",
		]);
		expect(fixture.lanes.find((lane) => lane.id === "G1-A")).toMatchObject({
			parentId: "G0",
			selected: true,
			runner_up: false,
			proofMode: "receipt_backed_fixture",
		});
		expect(fixture.lanes.find((lane) => lane.id === "G1-B")).toMatchObject({
			parentId: "G0",
			selected: false,
			runner_up: true,
		});
		expect(fixture.lanes.find((lane) => lane.id === "G2")).toMatchObject({
			parentId: "G1-A",
			generation: 2,
		});
		expect(fixture.lineage?.spawns?.map((spawn) => `${spawn.parent_lane_id}->${spawn.child_lane_id}`)).toEqual([
			"G0->G1-A",
			"G0->G1-B",
			"G1-A->G2",
		]);
		const selected = fixture.lanes.find((lane) => lane.id === "G1-A")!;
		expect(selected.stdout?.join("\n")).toContain("run=arena-adaptive-lineage-20260720T144034Z");
		expect(selected.stdout?.join("\n")).toContain("judge_duration=1.195406s");
		expect(selected.cockpit).toBeUndefined();
		expect(selected.score_semantics?.rules?.vulnerable_original_confirmed).toBe(true);
		expect(selected.knowledge_packet?.parent_analysis).toMatchObject({ parent_id: "G0", mutation_operator: "method_replace" });
		expect(fixture.lanes.find((lane) => lane.id === "G2")?.stdout?.join("\n")).toContain("novelty=4");
		expect(fixture.events.some((event) => event.summary.includes("Selection: G1-A over G1-B"))).toBe(true);
		expect(JSON.stringify(fixture)).not.toContain("20260719");
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

		const recalled = receiptBeatsVisibleAtPlayhead(collectReceiptBeats(fixture, fixture.lanes), 2.1, 3);
		expect(recalled.map((beat) => beat.react.liveEvent.notification)).toEqual([
			"Adaptive memory — RED G3 MEMORY CHILD: MEMORY RECALLED",
			"Adaptive memory — BLUE G3 MEMORY CHILD: MEMORY WRITTEN",
			"Adaptive memory — BLUE G3 MEMORY CHILD: MEMORY RECALLED",
		]);
		expect(recalled.every((beat) => beat.react.soundCue === "none" && beat.pixi.emphasis === "none")).toBe(true);
	});

	it("fails closed when V14 memory use is presented as improvement", async () => {
		const source = await memoryFixture();
		source.renderer_contract.memory_use_is_not_improvement = false;
		const result = validateAdaptiveLineageFixture(source);
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.error.detail).toMatch(/claim gates/i);
	});
});
