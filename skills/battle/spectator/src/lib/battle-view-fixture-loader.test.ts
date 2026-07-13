import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { discriminateBattleViewFixture } from "./battle-view-fixture-loader";
import { BATTLE_FIXTURE_RENDERERS, battleFixtureRegistryEntry, isSupportedBattleFixtureSchema } from "./battle-view-fixture-registry";
import { BATTLE_VIEW_FIXTURE_SCHEMAS } from "./battle-view-fixture";

async function loadJson(rel: string) {
	return JSON.parse(await readFile(resolve(import.meta.dirname, rel), "utf8"));
}

describe("battle fixture registry", () => {
	it("maps known schemas to renderers", () => {
		expect(BATTLE_FIXTURE_RENDERERS[BATTLE_VIEW_FIXTURE_SCHEMAS.RACE]?.renderer).toBe("BattleSpectatorArena");
		expect(BATTLE_FIXTURE_RENDERERS[BATTLE_VIEW_FIXTURE_SCHEMAS.PROOF_CARD]?.renderer).toBe("BattleProofCardPage");
		expect(BATTLE_FIXTURE_RENDERERS[BATTLE_VIEW_FIXTURE_SCHEMAS.SYNTHESIS]?.renderer).toBe("BattleSynthesisPage");
		expect(BATTLE_FIXTURE_RENDERERS[BATTLE_VIEW_FIXTURE_SCHEMAS.COMPILE]?.renderer).toBe("BattleCompilePage");
		expect(BATTLE_FIXTURE_RENDERERS[BATTLE_VIEW_FIXTURE_SCHEMAS.RUNTIME_JUDGE]?.renderer).toBe("BattleRuntimePage");
		expect(BATTLE_FIXTURE_RENDERERS[BATTLE_VIEW_FIXTURE_SCHEMAS.POPULATION]?.renderer).toBe("BattlePopulationPage");
		expect(isSupportedBattleFixtureSchema(BATTLE_VIEW_FIXTURE_SCHEMAS.SYNTHESIS)).toBe(true);
		expect(isSupportedBattleFixtureSchema(BATTLE_VIEW_FIXTURE_SCHEMAS.COMPILE)).toBe(true);
		expect(isSupportedBattleFixtureSchema(BATTLE_VIEW_FIXTURE_SCHEMAS.RUNTIME_JUDGE)).toBe(true);
		expect(isSupportedBattleFixtureSchema(BATTLE_VIEW_FIXTURE_SCHEMAS.POPULATION)).toBe(true);
		expect(battleFixtureRegistryEntry("battle.unknown.v1")).toBeNull();
	});
});

describe("discriminateBattleViewFixture", () => {
	it("accepts race fixture on race route", async () => {
		const data = await loadJson("../../public/battle-fixtures/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json");
		const result = discriminateBattleViewFixture(data, "race");
		expect(result.ok).toBe(true);
		if (result.ok) {
			expect(result.viewKind).toBe("race");
			expect(result.schema).toBe(BATTLE_VIEW_FIXTURE_SCHEMAS.RACE);
		}
	});

	it("accepts the validated adaptive lineage source on the race route", async () => {
		const data = await loadJson("../../public/battle-fixtures/battle-004-adaptive-lineage-v13/battle.normalized_ux_fixture.json");
		const result = discriminateBattleViewFixture(data, "race");
		expect(result.ok).toBe(true);
		if (result.ok) {
			expect(result.viewKind).toBe("race");
			expect(result.schema).toBe(BATTLE_VIEW_FIXTURE_SCHEMAS.ADAPTIVE_LINEAGE);
		}
	});

	it("accepts proof-card fixture on proof-card route", async () => {
		const data = await loadJson("../../public/battle-fixtures/battle-004-pr3b-proof-card/battle.normalized_proof_card_fixture.json");
		const result = discriminateBattleViewFixture(data, "proof-card");
		expect(result.ok).toBe(true);
		if (result.ok) {
			expect(result.viewKind).toBe("proof-card");
			expect(result.schema).toBe(BATTLE_VIEW_FIXTURE_SCHEMAS.PROOF_CARD);
		}
	});

	it("fails closed when proof-card fixture is forced onto race route", async () => {
		const data = await loadJson("../../public/battle-fixtures/battle-004-pr3b-proof-card/battle.normalized_proof_card_fixture.json");
		const result = discriminateBattleViewFixture(data, "race");
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.error.code).toBe("SCHEMA_ROUTE_MISMATCH");
	});

	it("fails closed when race fixture is forced onto proof-card route", async () => {
		const data = await loadJson("../../public/battle-fixtures/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json");
		const result = discriminateBattleViewFixture(data, "proof-card");
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.error.code).toBe("SCHEMA_ROUTE_MISMATCH");
	});

	it("accepts synthesis fixture on synthesis route", async () => {
		const data = await loadJson("../../public/battle-fixtures/battle-004-pr3c-synthesis/battle.normalized_synthesis_fixture.json");
		const result = discriminateBattleViewFixture(data, "synthesis");
		expect(result.ok).toBe(true);
		if (result.ok) {
			expect(result.viewKind).toBe("synthesis");
			expect(result.schema).toBe(BATTLE_VIEW_FIXTURE_SCHEMAS.SYNTHESIS);
		}
	});

	it("fails closed when synthesis fixture is forced onto race route", async () => {
		const data = await loadJson("../../public/battle-fixtures/battle-004-pr3c-synthesis/battle.normalized_synthesis_fixture.json");
		const result = discriminateBattleViewFixture(data, "race");
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.error.code).toBe("SCHEMA_ROUTE_MISMATCH");
	});

	it("accepts compile fixture on compile route", async () => {
		const data = await loadJson("../../public/battle-fixtures/battle-004-pr3d-compile/battle.normalized_compile_fixture.json");
		const result = discriminateBattleViewFixture(data, "compile");
		expect(result.ok).toBe(true);
		if (result.ok) {
			expect(result.viewKind).toBe("compile");
			expect(result.schema).toBe(BATTLE_VIEW_FIXTURE_SCHEMAS.COMPILE);
		}
	});

	it("fails closed when compile fixture is forced onto synthesis route", async () => {
		const data = await loadJson("../../public/battle-fixtures/battle-004-pr3d-compile/battle.normalized_compile_fixture.json");
		const result = discriminateBattleViewFixture(data, "synthesis");
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.error.code).toBe("SCHEMA_ROUTE_MISMATCH");
	});

	it("accepts runtime fixture on runtime route", async () => {
		const data = await loadJson("../../public/battle-fixtures/battle-004-pr4-runtime-judge/battle.normalized_runtime_judge_fixture.json");
		const result = discriminateBattleViewFixture(data, "runtime");
		expect(result.ok).toBe(true);
		if (result.ok) {
			expect(result.viewKind).toBe("runtime");
			expect(result.schema).toBe(BATTLE_VIEW_FIXTURE_SCHEMAS.RUNTIME_JUDGE);
		}
	});

	it("fails closed when runtime fixture is forced onto compile route", async () => {
		const data = await loadJson("../../public/battle-fixtures/battle-004-pr4-runtime-judge/battle.normalized_runtime_judge_fixture.json");
		const result = discriminateBattleViewFixture(data, "compile");
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.error.code).toBe("SCHEMA_ROUTE_MISMATCH");
	});

	it("accepts population fixture on population route", async () => {
		const data = await loadJson("../../public/battle-fixtures/battle-004-pr5-population/battle.normalized_population_fixture.json");
		const result = discriminateBattleViewFixture(data, "population");
		expect(result.ok).toBe(true);
		if (result.ok) {
			expect(result.viewKind).toBe("population");
			expect(result.schema).toBe(BATTLE_VIEW_FIXTURE_SCHEMAS.POPULATION);
		}
	});

	it("fails closed when population fixture is forced onto runtime route", async () => {
		const data = await loadJson("../../public/battle-fixtures/battle-004-pr5-population/battle.normalized_population_fixture.json");
		const result = discriminateBattleViewFixture(data, "runtime");
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.error.code).toBe("SCHEMA_ROUTE_MISMATCH");
	});

	it("fails closed on unknown schema", () => {
		const result = discriminateBattleViewFixture({ schema: "battle.normalized.unknown.v1", lanes: [] }, "race");
		expect(result.ok).toBe(false);
		if (!result.ok) {
			expect(result.error.code).toBe("UNSUPPORTED_SCHEMA");
			expect(result.error.detail).toMatch(/not yet supported|Unknown fixture schema/);
		}
	});

	it("fails closed when race fixture lacks lanes", () => {
		const result = discriminateBattleViewFixture({ schema: BATTLE_VIEW_FIXTURE_SCHEMAS.RACE }, "race");
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.error.code).toBe("CONTRACT_VALIDATION_FAILED");
	});
});
