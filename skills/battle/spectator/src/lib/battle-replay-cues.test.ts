import { describe, expect, it } from "vitest";
import type { BattleEvent, Lane, LaneEvent } from "./battle-types";
import { collectReplayCueCrossings, replayTickerEventsForPlayhead } from "./battle-replay-cues";
import { KILL_SHOT_TRAVEL_SECONDS } from "../engine/battle-pixi-kill-shot";

const fixture = {
	schema: "battle.normalized_ux_fixture.v1" as const,
	battle_id: "battle-004",
	proof_mode: "receipt_backed_fixture" as const,
	generated_at: "2026-01-01T00:00:00Z",
	lanes: [],
	events: [],
	leaderboard: [],
	receipts: [],
	timeline_elapsed_axis_model: { x_position_is_elapsed_time: true },
};

function laneEvent(partial: Partial<LaneEvent> & Pick<LaneEvent, "id" | "kind" | "x">): LaneEvent {
	return { proven: true, ...partial };
}

describe("collectReplayCueCrossings", () => {
	const lanes: Lane[] = [
		{
			id: "payload-857-receipt",
			name: "Red-0",
			payloadId: "payload-857-receipt",
			generation: 1,
			team: "red",
			xStart: 14,
			xEnd: 98,
			runnerX: 70,
			runnerState: "advance",
			lineColor: "red",
			terminal: "blocked",
			events: [
				laneEvent({ id: "blue", kind: "blue_blast", x: 67, elapsed_seconds: 100, animation: "blue_sonic_blast" }),
				laneEvent({ id: "judge", kind: "blocked", x: 82, elapsed_seconds: 101 }),
			],
		},
	];

	const battleEvents: BattleEvent[] = [
		{
			id: "blocked-event",
			ts: "2026-01-01T00:00:00Z",
			battle_id: "battle-004",
			team: "blue",
			actor_id: "blue-0",
			actor_kind: "patch_agent",
			event_type: "blue.blocked_red",
			summary: "Judge verified block",
			proof_mode: "receipt_backed_fixture",
			red_lane_id: "payload-857-receipt",
			ui: { notification: "Blue blocks Red exploit", sound_cue: "blue_blast", importance: "hero" },
		},
	];

	it("fires kill shot and impact cues when crossing blue blast window", () => {
		const cues = collectReplayCueCrossings({
			prevSeconds: 99,
			nextSeconds: 100 + KILL_SHOT_TRAVEL_SECONDS + 0.1,
			fixture,
			lanes,
			battleEvents,
		});
		expect(cues.map((cue) => cue.cue)).toEqual(["blue_blast", "blocked"]);
		expect(cues[0]?.soundCue).toBe("blue_blast");
		expect(cues[1]?.notification).toBe("Still standing — RED-0 survives");
		expect(cues[1]?.highlight).toBe("RED-0 SURVIVES");
	});
});

describe("replayTickerEventsForPlayhead", () => {
	it("returns synthetic ticker rows for kill shot moments", () => {
		const lanes: Lane[] = [
			{
				id: "payload-857-receipt",
				name: "Red-0",
				payloadId: "payload-857-receipt",
				generation: 1,
				team: "red",
				xStart: 14,
				xEnd: 98,
				runnerX: 70,
				runnerState: "advance",
				lineColor: "red",
				terminal: "blocked",
				events: [laneEvent({ id: "blue", kind: "blue_blast", x: 67, elapsed_seconds: 100, animation: "blue_sonic_blast" })],
			},
		];
		const rows = replayTickerEventsForPlayhead([], fixture, lanes, 100.2);
		expect(rows.at(-1)?.ui?.notification).toContain("locked on");
		expect(rows.at(-1)?.ui?.notification_highlight).toBe("LOCKED ON RED-0");
	});
});


describe("hunger games ticker overlay", () => {
	it("overrides matched receipt events with arena elimination copy", () => {
		const lanes: Lane[] = [
			{
				id: "payload-857-receipt",
				name: "Red-0",
				payloadId: "payload-857-receipt",
				generation: 1,
				team: "red",
				xStart: 14,
				xEnd: 98,
				runnerX: 70,
				runnerState: "advance",
				lineColor: "red",
				terminal: "blocked",
				events: [
					laneEvent({ id: "blue", kind: "blue_blast", x: 67, elapsed_seconds: 100, animation: "blue_sonic_blast" }),
					laneEvent({ id: "judge", kind: "blocked", x: 82, elapsed_seconds: 101 }),
				],
			},
		];
		const battleEvents: BattleEvent[] = [
			{
				id: "blocked-event",
				ts: "2026-01-01T00:00:00Z",
				battle_id: "battle-004",
				team: "blue",
				actor_id: "blue-0",
				actor_kind: "patch_agent",
				event_type: "blue.blocked_red",
				summary: "Judge verified block",
				proof_mode: "receipt_backed_fixture",
				red_lane_id: "payload-857-receipt",
				ui: { notification: "Blue blocks Red exploit", sound_cue: "blue_blast", importance: "hero" },
			},
		];
		const rows = replayTickerEventsForPlayhead(battleEvents, fixture, lanes, 100 + KILL_SHOT_TRAVEL_SECONDS + 0.1);
		expect(rows.at(-1)?.ui?.notification_highlight).toBe("RED-0 SURVIVES");
	});
});
