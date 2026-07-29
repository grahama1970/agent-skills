import type { BattleLiveEventV1 } from "./battle-transport-types";
import type { BattleLiveTransportContractV1 } from "./battle-live-transport-contract-types";
import { applyTransportEvent, type BattleTransportState } from "./battle-transport-reducer";

export type BattleLiveSseClientStatus =
	| "idle"
	| "contract_only_blocked"
	| "adapter_unavailable"
	| "connecting"
	| "open"
	| "gap_recovery"
	| "error"
	| "closed"
	| "ended";

export type BattleLiveSseClientState = {
	status: BattleLiveSseClientStatus;
	lastSeq: number;
	lastEventId: string | null;
	error: string | null;
	endpoint: string | null;
	baseUrl: string | null;
	live: "contract_only" | "local_http_sse_adapter" | "local_http_websocket_adapter" | null;
	/** How the stream is opened once serve-live-transport is up. */
	transportMode: "none" | "event_source" | "fetch_last_event_id" | "websocket";
};

export function createIdleLiveSseClientState(): BattleLiveSseClientState {
	return {
		status: "idle",
		lastSeq: 0,
		lastEventId: null,
		error: null,
		endpoint: null,
		baseUrl: null,
		live: null,
		transportMode: "none",
	};
}

export function planLiveWebSocketClient(
	contract: BattleLiveTransportContractV1,
	options?: { adapterAvailable?: boolean; baseUrl?: string | null },
): BattleLiveSseClientState {
	const endpoint = contract.websocket?.endpoint ?? null;
	if (!endpoint || !options?.adapterAvailable) {
		return {
			status: "contract_only_blocked",
			lastSeq: 0,
			lastEventId: null,
			error:
				"contract_only_blocked until ./run.sh serve-live-transport advertises a WebSocket endpoint from healthz.",
			endpoint,
			baseUrl: options?.baseUrl ?? null,
			live: "contract_only",
			transportMode: "none",
		};
	}
	return {
		status: "connecting",
		lastSeq: 0,
		lastEventId: null,
		error: null,
		endpoint,
		baseUrl: options?.baseUrl ?? null,
		live: "local_http_websocket_adapter",
		transportMode: "websocket",
	};
}

/**
 * Contract-aware SSE planner.
 * Published contracts remain live=contract_only. Executable adapter connection is a
 * separate runtime probe against the contract endpoint shapes.
 */
export function planLiveSseClient(
	contract: BattleLiveTransportContractV1,
	options?: { adapterAvailable?: boolean; baseUrl?: string | null },
): BattleLiveSseClientState {
	const endpoint = contract.transport.endpoint;
	if (!options?.adapterAvailable) {
		return {
			status: "contract_only_blocked",
			lastSeq: 0,
			lastEventId: null,
			error:
				"contract_only_blocked until ./run.sh serve-live-transport is running (healthz PASS). EventSource will not open.",
			endpoint,
			baseUrl: options?.baseUrl ?? null,
			live: "contract_only",
			transportMode: "none",
		};
	}
	return {
		status: "connecting",
		lastSeq: 0,
		lastEventId: null,
		error: null,
		endpoint,
		baseUrl: options?.baseUrl ?? null,
		live: "local_http_sse_adapter",
		transportMode: "event_source",
	};
}

export function parseSseLiveEventData(data: string): BattleLiveEventV1 | null {
	try {
		const parsed = JSON.parse(data) as BattleLiveEventV1;
		if (parsed?.schema !== "battle.live_event.v1") return null;
		if (typeof parsed.seq !== "number" || typeof parsed.event_id !== "string") return null;
		return parsed;
	} catch {
		return null;
	}
}

/** Apply one SSE payload through the shared transport reducer (dedupe + gap fail-closed). */
export function applySseLiveEvent(
	state: BattleTransportState,
	event: BattleLiveEventV1,
): BattleTransportState {
	return applyTransportEvent(state, event);
}

/**
 * True only when serve-live-transport was probed healthy.
 * Published contracts stay live=contract_only; runtime probe flips EventSource on.
 */
export function shouldOpenEventSource(
	contract: BattleLiveTransportContractV1,
	options?: { adapterAvailable?: boolean },
): boolean {
	return Boolean(options?.adapterAvailable) && contract.transport.kind === "sse";
}

export function shouldOpenWebSocket(
	contract: BattleLiveTransportContractV1,
	options?: { adapterAvailable?: boolean; websocketAvailable?: boolean },
): boolean {
	return Boolean(options?.adapterAvailable) && Boolean(options?.websocketAvailable) && contract.websocket?.kind === "websocket";
}
