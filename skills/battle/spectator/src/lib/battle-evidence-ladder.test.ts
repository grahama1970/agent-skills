import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { BattleNormalizedUxFixture } from "./battle-types";
import { geneticLifecycleViewModel } from "./battle-genetic-lifecycle";
import { buildEvidenceLadder } from "./battle-evidence-ladder";
import { buildLineageComparisonViewModel } from "./battle-lineage-comparison";

const fixturePath = resolve(
	import.meta.dirname,
	"../../public/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json",
);

describe("PR6 composite honesty + evidence ladder", () => {
	it("labels PR6 as composite demonstration with no causal continuity", () => {
		const fixture = JSON.parse(readFileSync(fixturePath, "utf8")) as BattleNormalizedUxFixture;
		const model = geneticLifecycleViewModel(fixture);
		expect(model?.compositeDemonstration).toBe(true);
		expect(model?.causalContinuityProven).toBe(false);
		expect(model?.sourceRunCount).toBeGreaterThanOrEqual(4);
		expect(model?.timelineSource).toBe("synthetic_presentation_order");
		expect(model?.presentationProofMode).toBe("composite_demonstration_fixture");
		expect(model?.mustNotClaim).toEqual(expect.arrayContaining(["causal_continuity_across_stage_fixtures"]));
	});

	it("builds an educational evidence ladder without inventing Judge success", () => {
		const fixture = JSON.parse(readFileSync(fixturePath, "utf8")) as BattleNormalizedUxFixture;
		const model = geneticLifecycleViewModel(fixture)!;
		const ladder = buildEvidenceLadder(model.present, model.notEmitted);
		expect(ladder.map((rung) => rung.id)).toEqual([
			"research",
			"generated",
			"compiled",
			"ran",
			"target_contact",
			"judge_verdict",
		]);
		expect(ladder.find((rung) => rung.id === "research")?.status).toBe("present");
		// judge_pending may be present on the composite fixture; that is not exploit success
		expect(model.notEmitted).toContain("judge_exploit_success");
		expect(model.notEmitted).toContain("genome_promoted");
		expect(ladder.find((rung) => rung.id === "judge_verdict")?.explanation).toMatch(/Judge determines/i);
	});

	it("builds a parent/child comparison preview without claiming adaptive intelligence", () => {
		const fixture = JSON.parse(readFileSync(fixturePath, "utf8")) as BattleNormalizedUxFixture;
		const comparison = buildLineageComparisonViewModel(fixture, true);
		expect(comparison?.parent?.laneId).toBe("payload-857-receipt");
		expect(comparison?.child?.laneId).toBe("payload-857-red-1");
		expect(comparison?.doesNotProve.join(" ")).toMatch(/adaptive intelligence|causal continuity/i);
	});
});
