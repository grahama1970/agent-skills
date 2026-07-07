import { describe, expect, it } from "vitest";
import type { Lane } from "../lib/battle-types";
import { runnerAnimationForLane } from "./battle-runner-animation";

function lane(partial: Partial<Lane> & Pick<Lane, "id">): Lane {
	return {
		name: partial.id,
		payloadId: partial.id,
		generation: 1,
		team: "red",
		xStart: 0,
		xEnd: 100,
		runnerX: 0,
		runnerState: "advance",
		lineColor: "red",
		terminal: "none",
		events: [],
		...partial,
	};
}

describe("runnerAnimationForLane", () => {
	it("maps active research segment to research animation", () => {
		const animation = runnerAnimationForLane(
			lane({
				id: "lane-a",
				activitySegments: [
					{
						id: "seg-1",
						phase: "research",
						label: "research",
						start_x: 10,
						end_x: 40,
						proof_mode: "receipt_backed_fixture",
					},
				],
			}),
			20,
			100,
		);
		expect(animation).toBe("research");
	});

	it("does not play killed before proven terminal event", () => {
		const animation = runnerAnimationForLane(
			lane({
				id: "lane-b",
				terminal: "killed",
				runnerState: "killed",
				events: [{ id: "e1", kind: "killed", x: 80, label: "KILLED", proven: false }],
			}),
			90,
			100,
		);
		expect(animation).not.toBe("killed");
	});

	it("plays blocked after proven blue gate event", () => {
		const animation = runnerAnimationForLane(
			lane({
				id: "lane-c",
				terminal: "blocked_handoff",
				activitySegments: [
					{
						id: "seg-block",
						phase: "patch_gate",
						label: "Blue patch gate",
						start_x: 60,
						end_x: 90,
						proof_mode: "receipt_backed_fixture",
					},
				],
				events: [{ id: "e-blue", kind: "blocked", x: 70, label: "BLUE BLOCK", proven: true }],
			}),
			75,
			100,
		);
		expect(animation).toBe("blocked");
	});
});
