import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { buildProofCardViewModel } from "../../lib/battle-proof-card-view-model";
import type { BattleNormalizedProofCardFixtureV1 } from "../../lib/battle-proof-card-types";

describe("ClaimBoundaryPanel data", () => {
	it("renders claim lists from fixture only", async () => {
		const fixture = JSON.parse(
			await readFile(
				resolve(import.meta.dirname, "../../../public/battle-fixtures/battle-004-pr3b-proof-card/battle.normalized_proof_card_fixture.json"),
				"utf8",
			),
		) as BattleNormalizedProofCardFixtureV1;
		const model = buildProofCardViewModel(fixture);
		expect(model.claimBoundary.mayClaim).toEqual(fixture.claim_boundary.may_claim.map((item) => item.replace(/_/g, " ")));
		expect(model.claimBoundary.mustNotClaim.join(" ")).toContain("exploit success");
		expect(model.claimBoundary.mayClaim.join(" ")).not.toContain("child exploit generated");
	});
});
