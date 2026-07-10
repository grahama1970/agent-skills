import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { buildCompileViewModel } from "./battle-compile-view-model";
import { validateCompileFixture, validateCompileSemantics } from "./battle-compile-validator";
import { battleCompileFixtureId, battleCompileFixtureUrl, isBattleCompileView } from "./battle-compile-registry";
import type { BattleNormalizedCompileFixtureV1 } from "./battle-compile-types";

async function loadFixture(): Promise<BattleNormalizedCompileFixtureV1> {
	return JSON.parse(
		await readFile(
			resolve(import.meta.dirname, "../../public/battle-fixtures/battle-004-pr3d-compile/battle.normalized_compile_fixture.json"),
			"utf8",
		),
	);
}

describe("compile routing", () => {
	it("resolves compile route and fixture", () => {
		expect(isBattleCompileView("#battle/compile?fixture=battle-004-pr3d")).toBe(true);
		expect(isBattleCompileView("#battle/synthesis?fixture=battle-004-pr3c")).toBe(false);
		expect(battleCompileFixtureId("#battle/compile?fixture=battle-004-pr3d")).toBe("battle-004-pr3d");
		expect(battleCompileFixtureId("#battle/compile?fixture=not-registered")).toBeNull();
		expect(battleCompileFixtureUrl("#battle/compile?fixture=battle-004-pr3d")).toContain("battle-004-pr3d-compile");
	});
});

describe("compile validator", () => {
	it("accepts the committed PR3d fixture", async () => {
		const fixture = await loadFixture();
		const result = validateCompileFixture(fixture);
		expect(result.ok).toBe(true);
	});

	it("fails closed on unknown schema", () => {
		const result = validateCompileFixture({ schema: "battle.normalized_synthesis_fixture.v1" });
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.error.code).toBe("UNSUPPORTED_SCHEMA");
	});

	it("fails closed when Tau command-loop paths leak in", async () => {
		const fixture = await loadFixture();
		const poisoned = {
			...fixture,
			receipt_refs: [...fixture.receipt_refs, { id: "x", schema: "x", status: "PASS", path: "command-loop/command-artifacts/foo" }],
		};
		const result = validateCompileFixture(poisoned);
		expect(result.ok).toBe(false);
	});
});

describe("compile view-model", () => {
	it("surfaces compile failed boundary without runnable claim", async () => {
		const fixture = await loadFixture();
		const model = buildCompileViewModel(fixture);
		expect(model.nodes.map((n) => n.id)).toContain("compile-repair");
		expect(model.compile.failed).toBe(true);
		expect(model.compile.passed).toBe(false);
		expect(model.repair.attempted).toBe(false);
		expect(model.versions.length).toBeGreaterThanOrEqual(2);
		expect(model.selectedVersion.id).toBe("v002");
		expect(model.banners.some((b) => b.label === "COMPILE FAILED")).toBe(true);
		expect(model.banners.some((b) => b.label === "NOT RUNNABLE")).toBe(true);
		expect(model.claimBoundary.compilePassedIsNotRunnable).toBe(true);
		expect(model.claimBoundary.mustNotClaim.some((item) => item.includes("runnable"))).toBe(true);
		expect(model.compile.stderrLines.some((line) => /SyntaxError/i.test(line))).toBe(true);
		expect(model.executionBoundary.find((row) => row.id === "runtime_status")?.value).toBe("NOT_RUN");
	});
});

describe("compile semantic guards", () => {
	it("rejects runtime_status other than NOT_RUN", async () => {
		const fixture = await loadFixture();
		const bad = {
			...fixture,
			execution_boundary: { ...fixture.execution_boundary, runtime_status: "PASS" as "NOT_RUN" },
		};
		expect(validateCompileSemantics(bad)?.detail).toMatch(/runtime_status/);
	});

	it("rejects missing runnable must-not-claim", async () => {
		const fixture = await loadFixture();
		const bad = {
			...fixture,
			claim_boundary: {
				...fixture.claim_boundary,
				must_not_claim: fixture.claim_boundary.must_not_claim.filter((item) => item !== "runnable"),
			},
		};
		expect(validateCompileSemantics(bad)?.detail).toMatch(/runnable/);
	});
});
