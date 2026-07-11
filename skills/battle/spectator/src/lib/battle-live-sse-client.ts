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
	live: "contract_only" | "local_http_sse_adapter" | null;
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
			status: contract.live === "contract_only" ? "contract_only_blocked" : "adapter_unavailable",
			lastSeq: 0,
			lastEventId: null,
			error:
				contract.live === "contract_only"
					? "SSE endpoint shape is defined by contract; local adapter not connected (live=contract_only)."
					: "Live SSE adapter unavailable.",
			endpoint,
			baseUrl: options?.baseUrl ?? null,
			live: "contract_only",
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

/** True only when a probed local adapter is available for the contract endpoints. */
export function shouldOpenEventSource(
	contract: BattleLiveTransportContractV1,
	options?: { adapterAvailable?: boolean },
): boolean {
	return Boolean(options?.adapterAvailable) && contract.transport.kind === "sse";
}
