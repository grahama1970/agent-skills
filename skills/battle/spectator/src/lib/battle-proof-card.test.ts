import { describe, expect, it } from "vitest";
import { battleProofCardFixtureUrl, isBattleProofCardView } from "./battle-proof-card-registry";
import { proofCardContainsForbiddenClaim } from "./battle-proof-card-compat";

describe("battle-proof-card routing compat", () => {
	it("detects proof hash routes", () => {
		expect(isBattleProofCardView("#battle/proof?fixture=battle-004-pr3b")).toBe(true);
		expect(battleProofCardFixtureUrl("#battle/proof?fixture=battle-004-pr3b")).toContain("battle-004-pr3b-proof-card");
	});

	it("flags forbidden claim phrases", () => {
		expect(proofCardContainsForbiddenClaim("Research and method genome produced")).toBeNull();
		expect(proofCardContainsForbiddenClaim("child exploit generated")).toBe("child exploit generated");
	});
});
