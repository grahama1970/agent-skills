import type { BattleLiveEventV1, BattleTransportStatus, BattleTransportViewModel } from "./battle-transport-types";
import type { BattleTransportPackage } from "./battle-transport-types";

export type BattleTransportState = {
	status: BattleTransportStatus;
	pack: BattleTransportPackage | null;
	appliedBySeq: Map<number, BattleLiveEventV1>;
	appliedByEventId: Map<string, BattleLiveEventV1>;
	appliedSeq: number;
	cursorSeconds: number;
	followLive: boolean;
	gapExpectedSeq: number | null;
	error: string | null;
};

export function createIdleTransportState(): BattleTransportState {
	return {
		status: "idle",
		pack: null,
		appliedBySeq: new Map(),
		appliedByEventId: new Map(),
		appliedSeq: 0,
		cursorSeconds: 0,
		followLive: true,
		gapExpectedSeq: null,
		error: null,
	};
}


/** Start following a live SSE stream from seq 0 after snapshot bootstrap. */
export function bootstrapLiveTransportState(pack: BattleTransportPackage): BattleTransportState {
	return {
		status: "ready",
		pack,
		appliedBySeq: new Map(),
		appliedByEventId: new Map(),
		appliedSeq: 0,
		cursorSeconds: 0,
		followLive: true,
		gapExpectedSeq: null,
		error: null,
	};
}
export function bootstrapTransportState(pack: BattleTransportPackage): BattleTransportState {
	const appliedBySeq = new Map<number, BattleLiveEventV1>();
	const appliedByEventId = new Map<string, BattleLiveEventV1>();
	for (const event of pack.events) {
		appliedBySeq.set(event.seq, event);
		appliedByEventId.set(event.event_id, event);
	}
	const liveSeconds = pack.events.at(-1)?.at_seconds ?? 0;
	return {
		status: pack.events.length ? "ended" : "ready",
		pack,
		appliedBySeq,
		appliedByEventId,
		appliedSeq: pack.manifest.last_seq,
		cursorSeconds: liveSeconds,
		followLive: true,
		gapExpectedSeq: null,
		error: null,
	};
}

/** Apply a single append-only event. Duplicates are ignored; gaps fail closed. */
export function applyTransportEvent(
	state: BattleTransportState,
	event: BattleLiveEventV1,
): BattleTransportState {
	if (state.appliedByEventId.has(event.event_id) || state.appliedBySeq.has(event.seq)) {
		return state;
	}
	const expected = state.appliedSeq + 1;
	if (event.seq !== expected) {
		return {
			...state,
			status: "gap_recovery",
			gapExpectedSeq: expected,
			error: `Sequence gap: expected seq ${expected}, got ${event.seq}. Reload snapshot.`,
			followLive: false,
		};
	}
	const appliedBySeq = new Map(state.appliedBySeq);
	const appliedByEventId = new Map(state.appliedByEventId);
	appliedBySeq.set(event.seq, event);
	appliedByEventId.set(event.event_id, event);
	const next: BattleTransportState = {
		...state,
		status: "following",
		appliedBySeq,
		appliedByEventId,
		appliedSeq: event.seq,
		gapExpectedSeq: null,
		error: null,
	};
	if (state.followLive) {
		next.cursorSeconds = event.at_seconds;
	}
	const lastSeq = state.pack?.manifest.last_seq ?? event.seq;
	if (event.seq >= lastSeq) {
		next.status = "ended";
	}
	return next;
}

/** Rebuild from snapshot + events after a gap (fail-closed recovery). */
export function recoverTransportFromPackage(pack: BattleTransportPackage): BattleTransportState {
	return bootstrapTransportState(pack);
}

export function setTransportFollowLive(state: BattleTransportState, followLive: boolean): BattleTransportState {
	const liveSeconds = liveCursorSeconds(state);
	const nextCursor = followLive ? liveSeconds : state.cursorSeconds;
	const nextStatus = followLive
		? state.appliedSeq >= (state.pack?.manifest.last_seq ?? 0)
			? "ended"
			: "following"
		: "scrubbing";
	if (state.followLive === followLive && Math.abs(state.cursorSeconds - nextCursor) < 0.001 && state.status === nextStatus) {
		return state;
	}
	return {
		...state,
		followLive,
		cursorSeconds: nextCursor,
		status: nextStatus,
	};
}

export function setTransportCursorSeconds(state: BattleTransportState, cursorSeconds: number): BattleTransportState {
	const next = Math.max(0, cursorSeconds);
	if (!state.followLive && state.status === "scrubbing" && Math.abs(state.cursorSeconds - next) < 0.001) {
		return state;
	}
	return {
		...state,
		cursorSeconds: next,
		followLive: false,
		status: "scrubbing",
	};
}

export function liveCursorSeconds(state: BattleTransportState): number {
	const events = [...state.appliedBySeq.values()].sort((a, b) => a.seq - b.seq);
	return events.at(-1)?.at_seconds ?? 0;
}

export function transportEventsVisibleAtCursor(state: BattleTransportState, limit = 3): BattleLiveEventV1[] {
	return [...state.appliedBySeq.values()]
		.filter((event) => event.at_seconds <= state.cursorSeconds + 0.001)
		.sort((a, b) => a.seq - b.seq)
		.slice(-limit);
}

export function transportViewModel(state: BattleTransportState): BattleTransportViewModel | null {
	if (!state.pack) return null;
	const { manifest } = state.pack;
	return {
		status: state.status,
		battleId: manifest.battle_id,
		runId: manifest.run_id,
		mode: manifest.mode,
		transport: manifest.stream_contract.transport,
		phase: manifest.stream_contract.phase,
		mocked: manifest.mocked,
		liveSource: manifest.live_source,
		eventCount: manifest.event_count,
		lastSeq: manifest.last_seq,
		appliedSeq: state.appliedSeq,
		cursorSeconds: state.cursorSeconds,
		liveSeconds: liveCursorSeconds(state),
		followLive: state.followLive,
		gapExpectedSeq: state.gapExpectedSeq,
		error: state.error,
		appliedEvents: [...state.appliedBySeq.values()].sort((a, b) => a.seq - b.seq),
	};
}
