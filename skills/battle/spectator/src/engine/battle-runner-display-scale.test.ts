import { describe, expect, it } from "vitest";
import { runnerDisplayScale } from "./battle-pixi-scene";

describe("runnerDisplayScale", () => {
	it("keeps runners compact inside the lane band", () => {
		const scale = runnerDisplayScale(92);
		expect(scale).toBeLessThanOrEqual(0.52);
		expect(scale * 64).toBeLessThan(92 * 0.4);
	});

	it("never returns near-full-row scale", () => {
		expect(runnerDisplayScale(92)).toBeLessThan(0.6);
		expect(runnerDisplayScale(86)).toBeLessThan(0.6);
	});
});
