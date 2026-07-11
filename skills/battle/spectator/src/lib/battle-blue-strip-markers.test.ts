import { describe, expect, it } from "vitest";
import { clusterBlueMarkers } from "./battle-blue-strip-markers";

describe("clusterBlueMarkers", () => {
	it("collapses same-x patches into one chip", () => {
		const clustered = clusterBlueMarkers([
			{ id: "a", label: "Patch A", left: 56, clock: "00:10" },
			{ id: "b", label: "Patch B", left: 56, clock: "00:10" },
		]);
		expect(clustered).toHaveLength(1);
		expect(clustered[0]?.stacked).toBe(2);
		expect(clustered[0]?.label).toMatch(/\+1/);
	});
});
