import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { buildProofCardViewModel } from "./battle-proof-card-view-model";
import { validateProofCardFixture, validateProofCardSemantics } from "./battle-proof-card-validator";
import { battleProofCardFixtureId, battleProofCardFixtureUrl, isBattleProofCardView } from "./battle-proof-card-registry";
import type { BattleNormalizedProofCardFixtureV1 } from "./battle-proof-card-types";

async function loadFixture(): Promise<BattleNormalizedProofCardFixtureV1> {
	return JSON.parse(
		await readFile(
			resolve(import.meta.dirname, "../../public/battle-fixtures/battle-004-pr3b-proof-card/battle.normalized_proof_card_fixture.json"),
			"utf8",
		),
	);
}

describe("proof-card routing", () => {
	it("resolves plan route and legacy alias", () => {
		expect(isBattleProofCardView("#battle/proof?fixture=battle-004-pr3b")).toBe(true);
		expect(isBattleProofCardView("#battle/proof-card?kind=pr3b-research-combiner")).toBe(true);
		expect(battleProofCardFixtureId("#battle/proof?fixture=battle-004-pr3b")).toBe("battle-004-pr3b");
		expect(battleProofCardFixtureId("#battle/proof-card?kind=pr3b-research-combiner")).toBe("battle-004-pr3b");
		expect(battleProofCardFixtureId("#battle/proof?fixture=not-registered")).toBeNull();
		expect(battleProofCardFixtureUrl("#battle/proof?fixture=battle-004-pr3b")).toContain("battle-004-pr3b-proof-card");
	});
});

describe("proof-card validator", () => {
	it("accepts the committed PR3b fixture", async () => {
		const fixture = await loadFixture();
		const result = validateProofCardFixture(fixture);
		expect(result.ok).toBe(true);
	});

	it("fails closed on unknown schema", () => {
		const result = validateProofCardFixture({ schema: "battle.normalized_ux_fixture.v1" });
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.error.code).toBe("UNSUPPORTED_SCHEMA");
	});

	it("fails closed when Tau command-loop paths leak in", async () => {
		const fixture = await loadFixture();
		const poisoned = {
			...fixture,
			receipt_refs: [...fixture.receipt_refs, { id: "x", schema: "x", status: "PASS", path: "command-loop/command-artifacts/foo" }],
		};
		const result = validateProofCardFixture(poisoned);
		expect(result.ok).toBe(false);
	});
});

describe("proof-card view-model", () => {
	it("orders nodes and groups methods", async () => {
		const fixture = await loadFixture();
		const model = buildProofCardViewModel(fixture);
		expect(model.nodes.map((node) => node.id)).toEqual([
			"lineage-summarizer",
			"research-scout",
			"method-combiner",
			"exploit-code-author",
		]);
		expect(model.nodes.filter((node) => node.status === "PASS")).toHaveLength(3);
		expect(model.nodes.find((node) => node.id === "exploit-code-author")?.treatment).toBe("blocked");
		expect(model.research.externalToolCalled).toBe(false);
		expect(model.research.providerLive).toBe(false);
		expect(model.methodGroups.find((group) => group.id === "selected")?.methods.length).toBeGreaterThan(0);
		expect(model.methodGroups.find((group) => group.id === "deferred")?.methods.length).toBeGreaterThan(0);
		expect(model.genome.notCodeLabel).toContain("NOT EXPLOIT CODE");
		expect(model.claimBoundary.mustNotClaim.some((item) => item.includes("exploit success"))).toBe(true);
		expect(model.badges.find((badge) => badge.id === "provider-live")?.value).toBe("NO");
	});
});

describe("proof-card semantic guards", () => {
	it("rejects wrong node statuses", async () => {
		const fixture = await loadFixture();
		const bad = {
			...fixture,
			node_status: { ...fixture.node_status, "exploit-code-author": "PASS" },
		};
		expect(validateProofCardSemantics(bad)?.detail).toMatch(/exploit-code-author/);
	});

	it("rejects missing must-not-claim entries", async () => {
		const fixture = await loadFixture();
		const bad = {
			...fixture,
			claim_boundary: {
				may_claim: fixture.claim_boundary.may_claim,
				must_not_claim: fixture.claim_boundary.must_not_claim.filter((item) => item !== "exploit_success"),
			},
		};
		expect(validateProofCardSemantics(bad)?.detail).toMatch(/exploit_success/);
	});

	it("rejects provider_live true", async () => {
		const fixture = await loadFixture();
		const bad = {
			...fixture,
			artifacts: {
				...fixture.artifacts,
				child_research_receipts: { ...fixture.artifacts.child_research_receipts, provider_live: true },
			},
		};
		expect(validateProofCardSemantics(bad)?.detail).toMatch(/provider_live/);
	});

	it("rejects external_tool_called true", async () => {
		const fixture = await loadFixture();
		const research = fixture.artifacts.child_research_receipts;
		const bad = {
			...fixture,
			artifacts: {
				...fixture.artifacts,
				child_research_receipts: {
					...research,
					query: { ...(research.query ?? {}), external_tool_called: true },
				},
			},
		};
		expect(validateProofCardSemantics(bad)?.detail).toMatch(/external_tool_called/);
	});
});
