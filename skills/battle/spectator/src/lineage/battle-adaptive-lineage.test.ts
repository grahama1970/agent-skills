import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { buildAdaptiveLineageViewModel } from "../lib/battle-adaptive-lineage";
import type { BattleAdaptiveLineageMechanicsFixtureV1 } from "../lib/battle-types";
import { BattleLineageComparisonPanel } from "./BattleLineageComparisonPanel";
import recordedFixtureJson from "./__fixtures__/adaptive-lineage-recorded.json";
import liveFixtureJson from "./__fixtures__/adaptive-lineage-live.json";

const recordedFixture = recordedFixtureJson as BattleAdaptiveLineageMechanicsFixtureV1;
const liveRunFixture = liveFixtureJson as BattleAdaptiveLineageMechanicsFixtureV1;

describe("buildAdaptiveLineageViewModel", () => {
	it("builds the G0 -> {G1-A, G1-B} -> G2 tree from receipt-sourced data", () => {
		const model = buildAdaptiveLineageViewModel(recordedFixture);
		expect(model).not.toBeNull();
		if (!model) return;

		expect(model.dataSource).toBe("recorded");
		expect(model.seed?.id).toBe("G0");
		expect(model.candidates.map((n) => n.id)).toEqual(["G1-A", "G1-B"]);
		expect(model.descendant?.id).toBe("G2");
		// G2 is parented to the selected G1.
		expect(model.descendant?.parentId).toBe(model.selection.selectedId);
	});

	it("exposes the deterministic selection and deciding criterion", () => {
		const model = buildAdaptiveLineageViewModel(recordedFixture)!;
		expect(model.selection.selectedId).toBe("G1-A");
		expect(model.selection.runnerUpId).toBe("G1-B");
		expect(model.selection.decidingCriterion).toBe("novelty_distance");
		expect(model.selected?.selected).toBe(true);
		expect(model.runnerUp?.runnerUp).toBe(true);
	});

	it("labels each mutation edge with operator, novelty, and changed dimensions", () => {
		const model = buildAdaptiveLineageViewModel(recordedFixture)!;
		const g2Edge = model.edges.find((e) => e.id === "G1-A->G2");
		expect(g2Edge?.mutationOperator).toBe("failure_guided_crossover");
		expect(g2Edge?.noveltyDistance).toBeGreaterThanOrEqual(2);
		expect(g2Edge?.changedDimensionNames).toContain("target_call_form");
		expect(g2Edge?.label).toContain("failure_guided_crossover");
	});

	it("badge distinguishes recorded (amber, not live) from live (green, proven)", () => {
		const recorded = buildAdaptiveLineageViewModel(recordedFixture)!;
		expect(recorded.badge.label).toBe("RECORDED · MECHANICS");
		expect(recorded.badge.tone).toBe("amber");
		expect(recorded.badge.provesLive).toBe(false);

		const liveFixture = { ...recordedFixture, data_source: "live" as const };
		const live = buildAdaptiveLineageViewModel(liveFixture)!;
		expect(live.badge.label).toBe("LIVE");
		expect(live.badge.tone).toBe("green");
		expect(live.badge.provesLive).toBe(true);
	});

	it("renders the real live BATTLE-004 qualification (run 6) as a proven LIVE PASS", () => {
		expect(liveRunFixture.data_source).toBe("live");
		const model = buildAdaptiveLineageViewModel(liveRunFixture)!;
		expect(model.badge.label).toBe("LIVE");
		expect(model.badge.provesLive).toBe(true);
		expect(model.qualification.status).toBe("PASS");
		expect(model.qualification.passed).toBe(true);
		expect(model.seed?.id).toBe("G0");
		const candidateOps = model.candidates.map((n) => [n.id, n.mutationOperator]);
		expect(candidateOps).toEqual([
			["G1-A", "method_replace"],
			["G1-B", "oracle_or_parameter_mutation"],
		]);
		expect(model.descendant?.mutationOperator).toBe("failure_guided_crossover");
		expect(model.selection.selectedId).toBe("G1-A");
		expect(model.selection.decidingCriterion).toBe("novelty_distance");
	});
});

describe("BattleLineageComparisonPanel (adaptive)", () => {
	const markup = renderToStaticMarkup(
		createElement(BattleLineageComparisonPanel, { adaptiveLineage: recordedFixture }),
	);

	it("renders the panel with a stable data-qid and adaptive mode", () => {
		expect(markup).toContain('data-qid="battle:lineage-comparison"');
		expect(markup).toContain('data-mode="adaptive"');
	});

	it("renders the RECORDED · MECHANICS data-source badge (amber, not proven live)", () => {
		expect(markup).toContain('data-qid="battle:adaptive-lineage:badge"');
		expect(markup).toContain('data-data-source="recorded"');
		expect(markup).toContain('data-proves-live="false"');
		expect(markup).toContain("RECORDED · MECHANICS");
	});

	it("renders the selected G1, runner-up, deciding criterion, and G2 operator", () => {
		expect(markup).toContain('data-qid="battle:adaptive-lineage:selected"');
		expect(markup).toContain('data-qid="battle:adaptive-lineage:runner-up"');
		expect(markup).toContain('data-deciding-criterion="novelty_distance"');
		expect(markup).toContain('data-selected-id="G1-A"');
		expect(markup).toContain('data-qid="battle:adaptive-lineage:node:G2"');
		expect(markup).toContain("failure_guided_crossover");
	});

	it("renders the changed AST dimensions for G2", () => {
		expect(markup).toContain('data-qid="battle:adaptive-lineage:node:G2:dimensions"');
		expect(markup).toContain("target_call_form");
	});

	it("shows the honesty note that recorded data does not prove a live canary", () => {
		expect(markup).toContain('data-qid="battle:adaptive-lineage:honesty"');
	});

	it("does not render the live badge or claim proven-live for recorded data", () => {
		expect(markup).not.toContain('data-proves-live="true"');
		expect(markup).not.toContain(">LIVE<");
	});
});
