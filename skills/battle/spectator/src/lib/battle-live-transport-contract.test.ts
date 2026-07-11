import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
	battleLiveTransportBattleId,
	battleLiveTransportMode,
	isBattleLiveView,
} from "./battle-transport-registry";
import { validateLiveTransportContract } from "./battle-live-transport-contract-validator";
import { liveTransportContractViewModel } from "./battle-live-transport-contract-loader";
import { planLiveSseClient, shouldOpenEventSource, parseSseLiveEventData } from "./battle-live-sse-client";
import type { BattleLiveTransportContractV1 } from "./battle-live-transport-contract-types";

const contractPath = resolve(
	import.meta.dirname,
	"../../public/battle-fixtures/battle-004-pr8-live-transport/battle.live_transport_contract.json",
);

function loadContract(): BattleLiveTransportContractV1 {
	return JSON.parse(readFileSync(contractPath, "utf8")) as BattleLiveTransportContractV1;
}

describe("UX8 live transport contract", () => {
	it("routes battle=battle-004 to contract mode", () => {
		const hash = "#battle/live?engine=pixi&battle=battle-004";
		expect(isBattleLiveView(hash)).toBe(true);
		expect(battleLiveTransportBattleId(hash)).toBe("battle-004");
		expect(battleLiveTransportMode(hash)).toBe("contract");
		expect(battleLiveTransportMode("#battle/live?fixture=battle-004-parent-spawn")).toBe("file_backed");
	});

	it("validates published contract claim boundary and genetic vocabulary", () => {
		const contract = loadContract();
		const validated = validateLiveTransportContract(contract);
		expect(validated.ok).toBe(true);
		expect(contract.live).toBe("contract_only");
		expect(contract.mocked).toBe(false);
		expect(contract.transport.kind).toBe("sse");
		expect(contract.event_stream.genetic_event_types_when_live).toHaveLength(16);
		expect(contract.claim_boundary.must_not_claim).toEqual(
			expect.arrayContaining([
				"sse_endpoint_implemented",
				"websocket_endpoint_implemented",
				"live_stream_executed",
				"live_genetic_events_emitted",
			]),
		);
		expect(contract.claim_boundary.live_contract_is_not_endpoint_execution).toBe(true);
	});

	it("stays contract_only_blocked until serve-live-transport is probed", () => {
		const contract = loadContract();
		expect(shouldOpenEventSource(contract)).toBe(false);
		expect(shouldOpenEventSource(contract, { adapterAvailable: false })).toBe(false);
		const planned = planLiveSseClient(contract);
		expect(planned.status).toBe("contract_only_blocked");
		expect(planned.transportMode).toBe("none");
		expect(planned.error).toMatch(/serve-live-transport/);
		expect(planned.endpoint).toBe("/battle/live/battle-004/events");
		const model = liveTransportContractViewModel(contract);
		expect(model.sseClientConnected).toBe(false);
		expect(model.endpointExecutionClaimed).toBe(false);
		expect(model.geneticEventCount).toBe(16);
	});

	it("parses SSE data payloads as battle.live_event.v1", () => {
		const ok = parseSseLiveEventData(
			JSON.stringify({
				schema: "battle.live_event.v1",
				run_id: "r",
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
					lane_id: "payload-857-red-1",
					exploit_id: "x",
					spawn_type: "",
					outcome_class: "unresolved_pressure",
					score_delta: {},
					receipt_id: "r1",
					presentation_owner: "ux",
					proof_mode: "receipt_backed_fixture",
				},
			}),
		);
		expect(ok?.seq).toBe(1);
		expect(parseSseLiveEventData("{bad")).toBeNull();
	});

	it("arms EventSource planner only when serve-live-transport probe passes", () => {
		const contract = loadContract();
		expect(shouldOpenEventSource(contract, { adapterAvailable: true })).toBe(true);
		const planned = planLiveSseClient(contract, {
			adapterAvailable: true,
			baseUrl: "http://127.0.0.1:18765",
		});
		expect(planned.status).toBe("connecting");
		expect(planned.live).toBe("local_http_sse_adapter");
		expect(planned.transportMode).toBe("event_source");
		expect(planned.baseUrl).toBe("http://127.0.0.1:18765");
	});

	it("resolves liveBase from hash", async () => {
		const { resolveBattleLiveTransportBaseUrl, buildLiveSseTransportPackage } = await import("./battle-live-sse-runtime");
		expect(
			resolveBattleLiveTransportBaseUrl("#battle/live?battle=battle-004&liveBase=http://127.0.0.1:19999/"),
		).toBe("http://127.0.0.1:19999");
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
			companionFixtureUrl: "/battle-fixtures/x.json",
		});
		expect(pack.manifest.mode).toBe("live_sse_adapter");
		expect(pack.manifest.stream_contract.transport).toBe("sse");
		expect(pack.manifest.live_source).toBe("local_http_sse_adapter");
	});

});
