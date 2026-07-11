import { describe, expect, it } from "vitest";
import { runnerDisplayScale } from "./battle-pixi-scene";

describe("runnerDisplayScale", () => {
	it("keeps runners readable inside the lane band", () => {
		const scale = runnerDisplayScale(92);
		expect(scale).toBeGreaterThanOrEqual(0.65);
		expect(scale).toBeLessThanOrEqual(1.15);
		expect(scale * 64).toBeGreaterThan(50);
	});

	it("never returns near-full-row scale", () => {
		expect(runnerDisplayScale(92)).toBeLessThan(1.2);
		expect(runnerDisplayScale(86)).toBeLessThan(1.2);
	});
});
