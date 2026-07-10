import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { buildRuntimeViewModel } from "./battle-runtime-view-model";
import { validateRuntimeJudgeFixture, validateRuntimeJudgeSemantics } from "./battle-runtime-validator";
import { battleRuntimeFixtureId, battleRuntimeFixtureUrl, isBattleRuntimeView } from "./battle-runtime-registry";
import type { BattleNormalizedRuntimeJudgeFixtureV1 } from "./battle-runtime-types";

async function loadFixture(): Promise<BattleNormalizedRuntimeJudgeFixtureV1> {
	return JSON.parse(
		await readFile(
			resolve(
				import.meta.dirname,
				"../../public/battle-fixtures/battle-004-pr4-runtime-judge/battle.normalized_runtime_judge_fixture.json",
			),
			"utf8",
		),
	);
}

describe("runtime routing", () => {
	it("resolves runtime route and fixture", () => {
		expect(isBattleRuntimeView("#battle/runtime?fixture=battle-004-pr4")).toBe(true);
		expect(isBattleRuntimeView("#battle/compile?fixture=battle-004-pr3d")).toBe(false);
		expect(battleRuntimeFixtureId("#battle/runtime?fixture=battle-004-pr4")).toBe("battle-004-pr4");
		expect(battleRuntimeFixtureId("#battle/runtime?fixture=not-registered")).toBeNull();
		expect(battleRuntimeFixtureUrl("#battle/runtime?fixture=battle-004-pr4")).toContain("battle-004-pr4-runtime-judge");
	});
});

describe("runtime validator", () => {
	it("accepts the committed PR4 fixture", async () => {
		const fixture = await loadFixture();
		const result = validateRuntimeJudgeFixture(fixture);
		expect(result.ok).toBe(true);
	});

	it("fails closed on unknown schema", () => {
		const result = validateRuntimeJudgeFixture({ schema: "battle.normalized_compile_fixture.v1" });
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.error.code).toBe("UNSUPPORTED_SCHEMA");
	});

	it("fails closed when Tau paths leak in", async () => {
		const fixture = await loadFixture();
		const poisoned = {
			...fixture,
			receipt_refs: [...fixture.receipt_refs, { id: "x", schema: "x", status: "PASS", path: "command-loop/command-artifacts/foo" }],
		};
		expect(validateRuntimeJudgeFixture(poisoned).ok).toBe(false);
	});
});

describe("runtime view-model", () => {
	it("surfaces docker runs and judge-not-run boundary", async () => {
		const fixture = await loadFixture();
		const model = buildRuntimeViewModel(fixture);
		expect(model.docker.image).toContain("python");
		expect(model.runs.length).toBe(4);
		expect(model.judge.status).toBe("NOT_RUN");
		expect(model.judge.verifiedExploits).toBe(0);
		expect(model.banners.some((b) => b.label === "JUDGE NOT RUN")).toBe(true);
		expect(model.banners.some((b) => b.label === "EXPLOIT SUCCESS NOT PROVEN")).toBe(true);
		expect(model.claimBoundary.targetContactIsNotExploitSuccess).toBe(true);
		expect(model.claimBoundary.mustNotClaim.some((item) => item.includes("exploit success"))).toBe(true);
		expect(model.summary.targetContactUnproven).toBeGreaterThan(0);
		expect(model.runs.some((run) => run.runtimeStatus === "TARGET_CONTACT_UNPROVEN")).toBe(true);
	});
});

describe("runtime semantic guards", () => {
	it("rejects judge verified exploits > 0", async () => {
		const fixture = await loadFixture();
		const bad = { ...fixture, judge: { ...fixture.judge, judge_verified_exploits: 1 } };
		expect(validateRuntimeJudgeSemantics(bad)?.detail).toMatch(/judge_verified_exploits/);
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
		expect(validateRuntimeJudgeSemantics(bad)?.detail).toMatch(/exploit_success/);
	});
});
