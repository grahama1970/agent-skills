import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { buildProofCardViewModel } from "../../lib/battle-proof-card-view-model";
import type { BattleNormalizedProofCardFixtureV1 } from "../../lib/battle-proof-card-types";

describe("ProofNodePipeline data", () => {
	it("exposes three PASS nodes and one BLOCKED author node", async () => {
		const fixture = JSON.parse(
			await readFile(
				resolve(import.meta.dirname, "../../../public/battle-fixtures/battle-004-pr3b-proof-card/battle.normalized_proof_card_fixture.json"),
				"utf8",
			),
		) as BattleNormalizedProofCardFixtureV1;
		const nodes = buildProofCardViewModel(fixture).nodes;
		expect(nodes.filter((node) => node.treatment === "pass")).toHaveLength(3);
		expect(nodes.find((node) => node.id === "exploit-code-author")?.treatment).toBe("blocked");
	});
});
