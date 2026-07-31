import { describe, expect, it } from "vitest";
import {
	absoluteLiveTransportUrl,
	buildLiveSseTransportPackage,
	resolveBattleLiveTransportBaseUrl,
	resolveBattleLiveTransportBaseCandidates,
	DEFAULT_BATTLE_LIVE_TRANSPORT_BASE,
} from "./battle-live-sse-runtime";
import { bootstrapLiveTransportState, applyTransportEvent } from "./battle-transport-reducer";
import type { BattleLiveEventV1 } from "./battle-transport-types";

describe("UX8 live SSE runtime", () => {
	it("defaults and overrides live transport base URL", () => {
		expect(resolveBattleLiveTransportBaseUrl("#battle/live?battle=battle-004")).toBe(
			DEFAULT_BATTLE_LIVE_TRANSPORT_BASE,
		);
		expect(
			resolveBattleLiveTransportBaseUrl("#battle/live?liveBase=http://127.0.0.1:9/"),
		).toBe("http://127.0.0.1:9");
		expect(absoluteLiveTransportUrl("http://127.0.0.1:18765", "/battle/live/battle-004/events")).toBe(
			"http://127.0.0.1:18765/battle/live/battle-004/events",
		);
		const candidates = resolveBattleLiveTransportBaseCandidates("#battle/live?battle=battle-004");
		expect(candidates[0]).toBe(DEFAULT_BATTLE_LIVE_TRANSPORT_BASE);
		expect(candidates).toContain("http://127.0.0.1:8765");
		expect(
			resolveBattleLiveTransportBaseCandidates("#battle/live?liveBase=http://127.0.0.1:59999"),
		).toEqual(["http://127.0.0.1:59999"]);
	});

	it("bootstraps live package at seq 0 then applies ordered events", () => {
		const pack = buildLiveSseTransportPackage({
			snapshot: {
				schema: "battle.snapshot.v1",
				battle_id: "battle-004",
				run_id: "run",
				last_seq: 2,
				generated_at: "2026-07-11T00:00:00Z",
				mode: "receipt_replay",
				events: [],
				lanes: [],
			},
			baseUrl: "http://127.0.0.1:18765",
			companionFixtureUrl: "/x.json",
		});
		let state = bootstrapLiveTransportState(pack);
		expect(state.appliedSeq).toBe(0);
		expect(state.status).toBe("ready");

		const event1 = {
			schema: "battle.live_event.v1",
			run_id: "run",
			battle_id: "battle-004",
			seq: 1,
			event_id: "e1",
			at_seconds: 1,
			observed_at: "2026-07-11T00:00:00Z",
			event_type: "research_started",
			payload: { receipt_id: "r1" },
			lifecycle: {
				schema: "battle.lifecycle_event.v1",
				source_time_seconds: 1,
				phase: "research",
				importance: "visible",
				lane_id: "lane-1",
				exploit_id: "x",
				spawn_type: "",
				outcome_class: "unresolved_pressure",
				score_delta: {},
				receipt_id: "r1",
				presentation_owner: "ux",
				proof_mode: "receipt_backed_fixture",
			},
		} as BattleLiveEventV1;
		state = applyTransportEvent(state, event1);
		expect(state.appliedSeq).toBe(1);
		expect(state.status).toBe("following");

		const event3 = { ...event1, seq: 3, event_id: "e3" };
		state = applyTransportEvent(state, event3);
		expect(state.status).toBe("gap_recovery");
	});
});
