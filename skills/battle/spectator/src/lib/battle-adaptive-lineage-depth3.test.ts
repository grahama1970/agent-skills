import { describe, it, expect } from "vitest";
import { validateAdaptiveLineageFixture } from "./battle-adaptive-lineage-validator";
import depth3 from "./battle-adaptive-lineage-depth3-sample.fixture.json";

// The sample is produced by the real Python converter (build_normalized_adaptive_fixture)
// from a full 41-event, 3-generation journal. It locks the depth-N (>2) rendering
// contract in the spectator validator independent of a live SciLLM run.
describe("depth-N (>2) adaptive lineage validator", () => {
	it("accepts a converter-produced 3-generation fixture: 6 lanes, 4 edges, 41 events", () => {
		const result = validateAdaptiveLineageFixture(depth3);
		expect(result.ok).toBe(true);
		if (result.ok) {
			expect(result.fixture.lanes.map((l) => l.lane_id)).toEqual([
				"red-g1", "red-g2", "red-g3", "blue-g1", "blue-g2", "blue-g3",
			]);
			expect(result.fixture.lineage_edges.length).toBe(4);
			expect(result.fixture.campaign.generation_count).toBe(3);
		}
	});
});
