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
		expect(isSupportedBattleFixtureSchema(BATTLE_VIEW_FIXTURE_SCHEMAS.SYNTHESIS)).toBe(false);
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

	it("fails closed on unknown schema", () => {
		const result = discriminateBattleViewFixture({ schema: "battle.normalized_synthesis_fixture.v1", lanes: [] }, "race");
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
