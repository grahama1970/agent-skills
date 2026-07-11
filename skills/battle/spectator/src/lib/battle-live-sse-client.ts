import type { BattleLiveEventV1 } from "./battle-transport-types";
import type { BattleLiveTransportContractV1 } from "./battle-live-transport-contract-types";
import { applyTransportEvent, type BattleTransportState } from "./battle-transport-reducer";

export type BattleLiveSseClientStatus =
	| "idle"
	| "contract_only_blocked"
	| "connecting"
	| "open"
	| "gap_recovery"
	| "error"
	| "closed";

export type BattleLiveSseClientState = {
	status: BattleLiveSseClientStatus;
	lastSeq: number;
	lastEventId: string | null;
	error: string | null;
	endpoint: string | null;
};

export function createIdleLiveSseClientState(): BattleLiveSseClientState {
	return {
		status: "idle",
		lastSeq: 0,
		lastEventId: null,
		error: null,
		endpoint: null,
	};
}

/**
 * Contract-aware SSE planner.
 * While live=contract_only, the client stays armed but must not open EventSource
 * or claim endpoint execution.
 */
export function planLiveSseClient(contract: BattleLiveTransportContractV1): BattleLiveSseClientState {
	if (contract.live === "contract_only") {
		return {
			status: "contract_only_blocked",
			lastSeq: 0,
			lastEventId: null,
			error: "SSE endpoint shape is defined by contract; endpoint execution is not claimed (live=contract_only).",
			endpoint: contract.transport.endpoint,
		};
	}
	return {
		status: "connecting",
		lastSeq: 0,
		lastEventId: null,
		error: null,
		endpoint: contract.transport.endpoint,
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

export function shouldOpenEventSource(contract: BattleLiveTransportContractV1): boolean {
	return contract.live !== "contract_only" && contract.transport.kind === "sse";
}
