import { describe, expect, it } from "vitest";
import type { LaneEvent } from "./battle-types";
import { layoutLaneEvents } from "./layout-lane-events";

function event(kind: LaneEvent["kind"], x: number, label?: string): LaneEvent {
	return { id: `${kind}-${x}`, kind, x, label };
}

describe("layoutLaneEvents", () => {
	it("keeps icons icon-only and text in bands", () => {
		const laidOut = layoutLaneEvents([
			event("research", 14, "ARENA SCENARIO"),
			event("handoff", 58, "SPAWN CHILD"),
			event("useful", 50, "EXPLOIT_CONFIRMED"),
		]);
		expect(laidOut.find((item) => item.kind === "handoff")?.labelBand).toBe("none");
		expect(laidOut.find((item) => item.kind === "research")?.labelBand).toBe("above");
		expect(laidOut.find((item) => item.kind === "useful")?.labelBand).toBe("below");
	});

	it("separates dense above labels", () => {
		const laidOut = layoutLaneEvents([event("research", 14, "ARENA SCENARIO"), event("payload", 18, "RED EXPLOIT")]);
		const above = laidOut.filter((item) => item.labelBand === "above").sort((a, b) => a.labelX - b.labelX);
		expect(above[1].labelX - above[0].labelX).toBeGreaterThan(10);
	});
});
