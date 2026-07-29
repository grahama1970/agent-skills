import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { buildSynthesisViewModel } from "./battle-synthesis-view-model";
import { validateSynthesisFixture, validateSynthesisSemantics } from "./battle-synthesis-validator";
import { battleSynthesisFixtureId, battleSynthesisFixtureUrl, isBattleSynthesisView } from "./battle-synthesis-registry";
import type { BattleNormalizedSynthesisFixtureV1 } from "./battle-synthesis-types";

async function loadFixture(): Promise<BattleNormalizedSynthesisFixtureV1> {
	return JSON.parse(
		await readFile(
			resolve(import.meta.dirname, "../../public/battle-fixtures/battle-004-pr3c-synthesis/battle.normalized_synthesis_fixture.json"),
			"utf8",
		),
	);
}

describe("synthesis routing", () => {
	it("resolves synthesis route and fixture", () => {
		expect(isBattleSynthesisView("#battle/synthesis?fixture=battle-004-pr3c")).toBe(true);
		expect(isBattleSynthesisView("#battle/proof?fixture=battle-004-pr3b")).toBe(false);
		expect(battleSynthesisFixtureId("#battle/synthesis?fixture=battle-004-pr3c")).toBe("battle-004-pr3c");
		expect(battleSynthesisFixtureId("#battle/synthesis?fixture=not-registered")).toBeNull();
		expect(battleSynthesisFixtureUrl("#battle/synthesis?fixture=battle-004-pr3c")).toContain("battle-004-pr3c-synthesis");
	});
});

describe("synthesis validator", () => {
	it("accepts the committed PR3c fixture", async () => {
		const fixture = await loadFixture();
		const result = validateSynthesisFixture(fixture);
		expect(result.ok).toBe(true);
	});

	it("fails closed on unknown schema", () => {
		const result = validateSynthesisFixture({ schema: "battle.normalized_proof_card_fixture.v1" });
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.error.code).toBe("UNSUPPORTED_SCHEMA");
	});

	it("fails closed when Tau command-loop paths leak in", async () => {
		const fixture = await loadFixture();
		const poisoned = {
			...fixture,
			receipt_refs: [...fixture.receipt_refs, { id: "x", schema: "x", status: "PASS", path: "command-loop/command-artifacts/foo" }],
		};
		const result = validateSynthesisFixture(poisoned);
		expect(result.ok).toBe(false);
	});
});

describe("synthesis view-model", () => {
	it("orders nodes and surfaces provider-authored boundary", async () => {
		const fixture = await loadFixture();
		const model = buildSynthesisViewModel(fixture);
		expect(model.nodes.map((node) => node.id)).toEqual([
			"lineage-summarizer",
			"research-scout",
			"method-combiner",
			"exploit-code-author",
		]);
		expect(model.nodes.every((node) => node.status === "PASS")).toBe(true);
		expect(model.provider.providerLive).toBe(true);
		expect(model.provider.requestIdPresent).toBe(true);
		expect(model.provider.responseIdPresent).toBe(true);
		expect(model.provider.callCount).toBe(1);
		expect(model.specimen.previewLines.length).toBeGreaterThan(0);
		expect(model.banners.map((b) => b.label)).toEqual([
			"PROVIDER-AUTHORED SPECIMEN",
			"NOT COMPILED",
			"NOT EXECUTED",
			"NOT JUDGE VERIFIED",
		]);
		expect(model.claimBoundary.mustNotClaim.some((item) => item.includes("compile passed"))).toBe(true);
		expect(model.claimBoundary.mustNotClaim.some((item) => item.includes("exploit success"))).toBe(true);
		expect(model.badges.find((badge) => badge.id === "provider-live")?.value).toBe("YES");
		expect(model.executionBoundary.find((row) => row.id === "compile_status")?.value).toBe("NOT_RUN");
	});
});

describe("synthesis semantic guards", () => {
	it("rejects provider_live false", async () => {
		const fixture = await loadFixture();
		const bad = { ...fixture, provider_live: false as unknown as true };
		expect(validateSynthesisSemantics(bad as BattleNormalizedSynthesisFixtureV1)?.detail).toMatch(/provider_live/);
	});

	it("rejects compile_status PASS", async () => {
		const fixture = await loadFixture();
		const bad = {
			...fixture,
			execution_boundary: { ...fixture.execution_boundary, compile_status: "PASS" },
		};
		expect(validateSynthesisSemantics(bad)?.detail).toMatch(/compile_status/);
	});

	it("rejects missing must-not-claim entries", async () => {
		const fixture = await loadFixture();
		const bad = {
			...fixture,
			claim_boundary: {
				may_claim: fixture.claim_boundary.may_claim,
				must_not_claim: fixture.claim_boundary.must_not_claim.filter((item) => item !== "compiled"),
			},
		};
		expect(validateSynthesisSemantics(bad)?.detail).toMatch(/compiled/);
	});
});
