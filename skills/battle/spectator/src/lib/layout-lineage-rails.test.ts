import { describe, expect, it } from "vitest";
import type { Lane } from "./battle-types";
import { computeLineageLayout, handoffTimelineX } from "./layout-lineage-rails";
import { trackPct } from "./utils";

const parent: Lane = {
	id: "parent",
	name: "Parent",
	payloadId: "payload-parent",
	generation: 1,
	team: "red",
	children: ["child-a"],
	xStart: 7,
	xEnd: 84,
	runnerX: 50,
	runnerState: "research",
	lineColor: "red",
	terminal: "none",
	events: [{ id: "h1", kind: "handoff", x: 58, label: "SPAWN" }],
};

const child: Lane = {
	id: "child-a",
	name: "Child",
	payloadId: "payload-child",
	generation: 2,
	team: "red",
	parentId: "parent",
	xStart: 62,
	xEnd: 90,
	runnerX: 40,
	runnerState: "research",
	lineColor: "green",
	terminal: "none",
	events: [],
};

describe("layout-lineage-rails", () => {
	it("derives handoff x from parent lane events", () => {
		expect(handoffTimelineX(parent)).toBe(58);
	});

	it("builds spawn-at-event branch from handoff column to child entry", () => {
		const layout = computeLineageLayout({
			lanes: [parent, child],
			rowRects: [
				{ id: "parent", top: 100, height: 112, trackLeft: 250, trackWidth: 900 },
				{ id: "child-a", top: 212, height: 112, trackLeft: 250, trackWidth: 900 },
			],
			collapsed: new Set(),
			containerTop: 80,
		});
		expect(layout.branches).toHaveLength(1);
		const branch = layout.branches[0];
		expect(branch.x).toBeCloseTo(250 + (trackPct(58) / 100) * 900, 1);
		expect(branch.childEntryX).toBeGreaterThan(branch.x);
		expect(branch.childY).toBeGreaterThan(branch.parentY);
	});
});
