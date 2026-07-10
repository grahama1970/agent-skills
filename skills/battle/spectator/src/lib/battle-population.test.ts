import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { buildPopulationViewModel } from "./battle-population-view-model";
import { validatePopulationFixture, validatePopulationSemantics } from "./battle-population-validator";
import { battlePopulationFixtureId, battlePopulationFixtureUrl, isBattlePopulationView } from "./battle-population-registry";
import type { BattleNormalizedPopulationFixtureV1 } from "./battle-population-types";

async function loadFixture(): Promise<BattleNormalizedPopulationFixtureV1> {
	return JSON.parse(
		await readFile(
			resolve(
				import.meta.dirname,
				"../../public/battle-fixtures/battle-004-pr5-population/battle.normalized_population_fixture.json",
			),
			"utf8",
		),
	);
}

describe("population routing", () => {
	it("resolves population route and fixture", () => {
		expect(isBattlePopulationView("#battle/population?fixture=battle-004-pr5-population")).toBe(true);
		expect(isBattlePopulationView("#battle/runtime?fixture=battle-004-pr4")).toBe(false);
		expect(battlePopulationFixtureId("#battle/population?fixture=battle-004-pr5-population")).toBe("battle-004-pr5-population");
		expect(battlePopulationFixtureId("#battle/population?fixture=not-registered")).toBeNull();
		expect(battlePopulationFixtureUrl("#battle/population?fixture=battle-004-pr5-population")).toContain(
			"battle-004-pr5-population",
		);
	});
});

describe("population validator", () => {
	it("accepts the committed PR5 fixture", async () => {
		const result = validatePopulationFixture(await loadFixture());
		expect(result.ok).toBe(true);
	});

	it("fails closed on unknown schema", () => {
		const result = validatePopulationFixture({ schema: "battle.normalized_runtime_judge_fixture.v1" });
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.error.code).toBe("UNSUPPORTED_SCHEMA");
	});

	it("fails closed when Tau paths leak in", async () => {
		const fixture = await loadFixture();
		const poisoned = {
			...fixture,
			receipt_refs: [...fixture.receipt_refs, { id: "x", schema: "x", status: "PASS", path: "command-loop/command-artifacts/foo" }],
		};
		expect(validatePopulationFixture(poisoned).ok).toBe(false);
	});
});

describe("population view-model", () => {
	it("surfaces specimens, generations, and lineage without exploit claims", async () => {
		const model = buildPopulationViewModel(await loadFixture());
		expect(model.specimens).toHaveLength(4);
		expect(model.generations).toHaveLength(4);
		expect(model.edges).toHaveLength(3);
		expect(model.campaign.fullEngineProven).toBe(false);
		expect(model.campaign.bestSpecimenId).toBe("specimen-0004");
		expect(model.banners.some((b) => b.label === "NOT FULL GENETIC ENGINE")).toBe(true);
		expect(model.claimBoundary.mustNotClaim.some((item) => item.includes("exploit success"))).toBe(true);
		expect(model.claimBoundary.notFullEngine).toBe(true);
		expect(model.specimens.every((s) => s.judgeStatus === "NOT_RUN")).toBe(true);
		expect(model.specimens.every((s) => s.providerLive === false)).toBe(true);
	});

	it("filters by generation", async () => {
		const model = buildPopulationViewModel(await loadFixture(), 3);
		expect(model.specimens).toHaveLength(1);
		expect(model.specimens[0]?.id).toBe("specimen-0004");
	});
});

describe("population semantic guards", () => {
	it("rejects full engine proven", async () => {
		const fixture = await loadFixture();
		const bad = {
			...fixture,
			campaign: { ...fixture.campaign, full_population_engine_proven: true as false },
		};
		expect(validatePopulationSemantics(bad)?.detail).toMatch(/full_population_engine_proven/);
	});

	it("rejects missing exploit_success must-not-claim", async () => {
		const fixture = await loadFixture();
		const bad = {
			...fixture,
			claim_boundary: {
				...fixture.claim_boundary,
				must_not_claim: fixture.claim_boundary.must_not_claim.filter((item) => item !== "exploit_success"),
			},
		};
		expect(validatePopulationSemantics(bad)?.detail).toMatch(/exploit_success/);
	});
});
