import { describe, expect, it } from "vitest";
import type { Lane, LaneEvent } from "../lib/battle-types";
import {
	KILL_SHOT_IMPACT_SECONDS,
	KILL_SHOT_TRAVEL_SECONDS,
	killShotVisualForEvent,
	resolveKillShotImpact,
} from "./battle-pixi-kill-shot";

function lane(partial: Partial<Lane> & Pick<Lane, "id">): Lane {
	return {
		name: partial.id,
		payloadId: partial.id,
		generation: 1,
		team: "red",
		xStart: 14,
		xEnd: 98,
		runnerX: 70,
		runnerState: "advance",
		lineColor: "red",
		terminal: "blocked",
		events: [],
		...partial,
	};
}

function event(partial: Partial<LaneEvent> & Pick<LaneEvent, "id" | "kind" | "x">): LaneEvent {
	return {
		label: partial.kind,
		proven: true,
		...partial,
	};
}

describe("resolveKillShotImpact", () => {
	it("resolves blocked after blue blast", () => {
		const blast = event({ id: "blue", kind: "blue_blast", x: 67, elapsed_seconds: 100, animation: "blue_sonic_blast" });
		const blocked = event({ id: "judge", kind: "blocked", x: 82, elapsed_seconds: 101 });
		expect(resolveKillShotImpact(lane({ id: "a", events: [blast, blocked] }), blast, 1200, true)).toBe("blocked");
	});

	it("prefers killed over blocked when both follow", () => {
		const blast = event({ id: "blue", kind: "blue_blast", x: 67, elapsed_seconds: 100 });
		const blocked = event({ id: "judge", kind: "blocked", x: 82, elapsed_seconds: 101 });
		const killed = event({ id: "kill", kind: "killed", x: 90, elapsed_seconds: 102 });
		expect(resolveKillShotImpact(lane({ id: "a", events: [blast, blocked, killed] }), blast, 1200, true)).toBe("killed");
	});
});

describe("killShotVisualForEvent", () => {
	const blast = event({ id: "blue", kind: "blue_blast", x: 67, elapsed_seconds: 100, animation: "blue_sonic_blast" });
	const testLane = lane({
		id: "payload-857-receipt",
		start_elapsed_seconds: 0,
		end_elapsed_seconds: 150,
		events: [blast, event({ id: "judge", kind: "blocked", x: 82, elapsed_seconds: 101 })],
	});

	it("is null before blast time", () => {
		expect(
			killShotVisualForEvent({
				lane: testLane,
				blastEvent: blast,
				rowY: 40,
				currentSeconds: 99,
				allottedSeconds: 1200,
				contentWidth: 1320,
				useElapsed: true,
			}),
		).toBeNull();
	});

	it("travels during the shot window", () => {
		const shot = killShotVisualForEvent({
			lane: testLane,
			blastEvent: blast,
			rowY: 40,
			currentSeconds: 100 + KILL_SHOT_TRAVEL_SECONDS * 0.5,
			allottedSeconds: 1200,
			contentWidth: 1320,
			useElapsed: true,
		});
		expect(shot?.phase).toBe("travel");
		expect(shot?.progress).toBeGreaterThan(0);
		expect(shot?.progress).toBeLessThan(1);
	});

	it("enters impact phase after travel completes", () => {
		const shot = killShotVisualForEvent({
			lane: testLane,
			blastEvent: blast,
			rowY: 40,
			currentSeconds: 100 + KILL_SHOT_TRAVEL_SECONDS + KILL_SHOT_IMPACT_SECONDS * 0.25,
			allottedSeconds: 1200,
			contentWidth: 1320,
			useElapsed: true,
		});
		expect(shot?.phase).toBe("impact");
		expect(shot?.impactKind).toBe("blocked");
		expect(shot?.impactAlpha).toBeGreaterThan(0.5);
	});
});
