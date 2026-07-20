import type { BattleLiveTransportContractV1 } from "./battle-live-transport-contract-types";
import type {
	BattleLiveEventV1,
	BattleSnapshotV1Full,
	BattleTransportLoadError,
	BattleTransportManifestV1,
	BattleTransportPackage,
} from "./battle-transport-types";
import { validateLiveEvent, validateSnapshot } from "./battle-transport-validator";
import { parseSseLiveEventData } from "./battle-live-sse-client";
import { battleHashSearchParams } from "./battle-transport-registry";

export const DEFAULT_BATTLE_LIVE_TRANSPORT_BASE = "http://127.0.0.1:18765";

/** Candidate bases for local `./run.sh serve-live-transport` (handoff 8765 + non-colliding 18765). */
export const BATTLE_LIVE_TRANSPORT_BASE_CANDIDATES = [
	"http://127.0.0.1:18765",
	"http://127.0.0.1:8765",
] as const;

export type BattleLiveAdapterProbe =
	| {
			ok: true;
			baseUrl: string;
			battleId: string;
			runId: string;
			eventCount: number;
			lastSeq: number;
			live: "local_http_sse_adapter";
	  }
	| { ok: false; error: BattleTransportLoadError };

export type BattleLiveSseStreamHandle = {
	close: () => void;
	done: Promise<void>;
};

function fail(detail: string, code: BattleTransportLoadError["code"] = "TRANSPORT_UNAVAILABLE"): BattleTransportLoadError {
	return {
		code,
		title: code === "TRANSPORT_UNAVAILABLE" ? "TRANSPORT UNAVAILABLE" : "CONTRACT VALIDATION FAILED",
		detail,
	};
}

function trimBase(url: string): string {
	return url.replace(/\/$/, "");
}

/** Resolve live SSE adapter base URL from hash ?liveBase= or default local adapter port. */
export function resolveBattleLiveTransportBaseUrl(
	hash = typeof window !== "undefined" ? window.location.hash : "",
): string {
	const params = battleHashSearchParams(hash);
	const fromHash = params.get("liveBase")?.trim();
	if (fromHash) return trimBase(fromHash);
	const fromEnv =
		typeof import.meta !== "undefined" &&
		import.meta.env &&
		typeof import.meta.env.VITE_BATTLE_LIVE_TRANSPORT_BASE === "string"
			? import.meta.env.VITE_BATTLE_LIVE_TRANSPORT_BASE.trim()
			: "";
	if (fromEnv) return trimBase(fromEnv);
	return DEFAULT_BATTLE_LIVE_TRANSPORT_BASE;
}

/** Ordered base URLs to probe for a running serve-live-transport adapter. */
export function resolveBattleLiveTransportBaseCandidates(
	hash = typeof window !== "undefined" ? window.location.hash : "",
): string[] {
	const params = battleHashSearchParams(hash);
	const explicit = params.get("liveBase")?.trim();
	// Explicit liveBase is fail-closed to that host only (prove/fallback paths).
	if (explicit) return [trimBase(explicit)];
	const primary = resolveBattleLiveTransportBaseUrl(hash);
	const out: string[] = [];
	const push = (value: string) => {
		const trimmed = trimBase(value);
		if (trimmed && !out.includes(trimmed)) out.push(trimmed);
	};
	push(primary);
	for (const candidate of BATTLE_LIVE_TRANSPORT_BASE_CANDIDATES) push(candidate);
	return out;
}

/** Probe candidate bases until serve-live-transport healthz returns PASS for this battle. */
export async function discoverBattleLiveTransportAdapter(args: {
	battleId: string;
	hash?: string;
}): Promise<BattleLiveAdapterProbe> {
	const bases = resolveBattleLiveTransportBaseCandidates(args.hash);
	let lastFail: BattleLiveAdapterProbe | null = null;
	for (const baseUrl of bases) {
		const probe = await probeBattleLiveTransportAdapter({ baseUrl, battleId: args.battleId });
		if (probe.ok) return probe;
		lastFail = probe;
	}
	return (
		lastFail ?? {
			ok: false,
			error: fail("serve-live-transport is not running on any known liveBase."),
		}
	);
}

export function absoluteLiveTransportUrl(baseUrl: string, endpoint: string): string {
	if (endpoint.startsWith("http://") || endpoint.startsWith("https://")) return endpoint;
	return `${trimBase(baseUrl)}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
}

export async function probeBattleLiveTransportAdapter(args: {
	baseUrl: string;
	battleId: string;
}): Promise<BattleLiveAdapterProbe> {
	const healthUrl = `${trimBase(args.baseUrl)}/healthz`;
	try {
		const response = await fetch(healthUrl, { headers: { Accept: "application/json" } });
		if (!response.ok) {
			return { ok: false, error: fail(`Live adapter healthz failed (${response.status}) at ${healthUrl}.`) };
		}
		const health = (await response.json()) as Record<string, unknown>;
		if (health.schema !== "battle.live_transport_health.v1" || health.status !== "PASS") {
			return { ok: false, error: fail("Live adapter healthz did not return battle.live_transport_health.v1 PASS.") };
		}
		if (health.battle_id !== args.battleId) {
			return {
				ok: false,
				error: fail(`Live adapter battle_id ${String(health.battle_id)} does not match ${args.battleId}.`),
			};
		}
		return {
			ok: true,
			baseUrl: trimBase(args.baseUrl),
			battleId: args.battleId,
			runId: String(health.run_id ?? ""),
			eventCount: Number(health.event_count ?? 0),
			lastSeq: Number(health.last_seq ?? 0),
			live: "local_http_sse_adapter",
		};
	} catch (error) {
		return {
			ok: false,
			error: fail(error instanceof Error ? error.message : `Failed to probe ${healthUrl}.`),
		};
	}
}

export async function fetchBattleLiveSnapshot(args: {
	baseUrl: string;
	snapshotEndpoint: string;
}): Promise<{ ok: true; snapshot: BattleSnapshotV1Full } | { ok: false; error: BattleTransportLoadError }> {
	const url = absoluteLiveTransportUrl(args.baseUrl, args.snapshotEndpoint);
	try {
		const response = await fetch(url, { headers: { Accept: "application/json" } });
		if (!response.ok) {
			return { ok: false, error: fail(`Snapshot fetch failed (${response.status}) at ${url}.`) };
		}
		return validateSnapshot(await response.json());
	} catch (error) {
		return {
			ok: false,
			error: fail(error instanceof Error ? error.message : `Failed to fetch snapshot ${url}.`),
		};
	}
}

/** Build a transport package shell from a live snapshot so the reducer can apply SSE events. */
export function buildLiveSseTransportPackage(args: {
	snapshot: BattleSnapshotV1Full;
	baseUrl: string;
	companionFixtureUrl: string;
	events?: BattleLiveEventV1[];
}): BattleTransportPackage {
	const events = args.events ?? [];
	const manifest: BattleTransportManifestV1 = {
		schema: "battle.transport_manifest.v1",
		battle_id: args.snapshot.battle_id,
		run_id: args.snapshot.run_id,
		mode: "live_sse_adapter",
		mocked: false,
		live_source: "local_http_sse_adapter",
		event_count: args.snapshot.last_seq,
		last_seq: args.snapshot.last_seq,
		events_jsonl: "events.jsonl",
		latest_snapshot: "latest-snapshot.json",
		normalized_fixture_schema: "battle.normalized_ux_fixture.v1",
		proof_mode: "receipt_backed_fixture",
		stream_contract: {
			schema: "battle.stream_contract.v1",
			authority: "backend_receipts_to_normalized_snapshot_and_events_to_renderer",
			event_schema: "battle.live_event.v1",
			snapshot_schema: "battle.snapshot.v1",
			lifecycle_schema: "battle.lifecycle_event.v1",
			transport: "sse",
			phase: "local_http_sse_adapter",
			fail_closed_unknown_terminal_states: true,
		},
		replay_compression_policy: args.snapshot.replay_compression_policy,
		source_time_window: args.snapshot.source_time_window,
		renderer_boundary: args.snapshot.renderer_boundary,
	};
	return {
		manifest,
		snapshot: args.snapshot,
		events,
		streamBaseUrl: trimBase(args.baseUrl),
		companionFixtureUrl: args.companionFixtureUrl,
	};
}

/**
 * Open live SSE.
 * - Prefer native EventSource when starting from seq 0 (serve-live-transport running).
 * - Use fetch + Last-Event-ID only for explicit resume/gap recovery (EventSource cannot set it on first connect).
 */
export function openBattleLiveSseStream(args: {
	baseUrl: string;
	eventsEndpoint: string;
	lastEventId?: number | null;
	onEvent: (event: BattleLiveEventV1) => void;
	onError?: (error: string) => void;
	onOpen?: () => void;
	signal?: AbortSignal;
}): BattleLiveSseStreamHandle {
	const lastEventId = args.lastEventId ?? 0;
	if (lastEventId > 0) {
		return openBattleLiveSseStreamWithFetch(args);
	}
	return openBattleLiveEventSource(args);
}

/** Native EventSource path — only call after serve-live-transport healthz PASS. */
export function openBattleLiveEventSource(args: {
	baseUrl: string;
	eventsEndpoint: string;
	onEvent: (event: BattleLiveEventV1) => void;
	onError?: (error: string) => void;
	onOpen?: () => void;
	signal?: AbortSignal;
}): BattleLiveSseStreamHandle {
	const url = absoluteLiveTransportUrl(args.baseUrl, args.eventsEndpoint);
	let closed = false;
	let source: EventSource | null = null;
	let settle!: () => void;
	const done = new Promise<void>((resolve) => {
		settle = resolve;
	});

	const close = () => {
		if (closed) return;
		closed = true;
		source?.close();
		source = null;
		settle();
	};

	if (args.signal) {
		if (args.signal.aborted) {
			close();
			return { close, done };
		}
		args.signal.addEventListener("abort", close, { once: true });
	}

	try {
		source = new EventSource(url);
	} catch (error) {
		args.onError?.(error instanceof Error ? error.message : "EventSource open failed.");
		close();
		return { close, done };
	}

	const handlePayload = (raw: string) => {
		const parsed = parseSseLiveEventData(raw);
		if (!parsed) {
			args.onError?.("SSE frame was not battle.live_event.v1; fail-closed.");
			close();
			return;
		}
		const validated = validateLiveEvent(parsed);
		if (!validated.ok) {
			args.onError?.(validated.error.detail);
			close();
			return;
		}
		args.onEvent(validated.event);
	};

	source.addEventListener("battle.live_event", (event) => {
		handlePayload((event as MessageEvent).data);
	});
	source.onmessage = (event) => {
		handlePayload(event.data);
	};
	source.onopen = () => {
		args.onOpen?.();
	};
	source.onerror = () => {
		// Finite serve-live-transport streams close after the last event. Close without
		// forcing a browser reconnect loop; callers decide if seq was complete.
		if (!source) return;
		if (source.readyState === EventSource.CONNECTING || source.readyState === EventSource.CLOSED) {
			close();
		}
	};

	return { close, done };
}

/** Fetch SSE with Last-Event-ID — used for gap/resume only. */
export function openBattleLiveSseStreamWithFetch(args: {
	baseUrl: string;
	eventsEndpoint: string;
	lastEventId?: number | null;
	onEvent: (event: BattleLiveEventV1) => void;
	onError?: (error: string) => void;
	onOpen?: () => void;
	signal?: AbortSignal;
}): BattleLiveSseStreamHandle {
	const controller = new AbortController();
	const onAbort = () => controller.abort();
	if (args.signal) {
		if (args.signal.aborted) controller.abort();
		else args.signal.addEventListener("abort", onAbort, { once: true });
	}

	const url = absoluteLiveTransportUrl(args.baseUrl, args.eventsEndpoint);
	const headers: Record<string, string> = {
		Accept: "text/event-stream",
	};
	if (args.lastEventId != null && args.lastEventId > 0) {
		headers["Last-Event-ID"] = String(args.lastEventId);
	}

	const done = (async () => {
		try {
			const response = await fetch(url, {
				headers,
				signal: controller.signal,
			});
			if (!response.ok || !response.body) {
				args.onError?.(
					response.status === 400
						? `SSE resume rejected (${response.status}); refetch snapshot.`
						: `SSE open failed (${response.status}) at ${url}.`,
				);
				return;
			}
			args.onOpen?.();
			const reader = response.body.getReader();
			const decoder = new TextDecoder();
			let buffer = "";
			while (true) {
				const { done: finished, value } = await reader.read();
				if (finished) break;
				buffer += decoder.decode(value, { stream: true });
				const frames = buffer.split("\n\n");
				buffer = frames.pop() ?? "";
				for (const frame of frames) {
					const dataLines = frame
						.split("\n")
						.filter((line) => line.startsWith("data:"))
						.map((line) => line.slice(5).trimStart());
					if (!dataLines.length) continue;
					const parsed = parseSseLiveEventData(dataLines.join("\n"));
					if (!parsed) {
						args.onError?.("SSE frame was not battle.live_event.v1; fail-closed.");
						controller.abort();
						return;
					}
					const validated = validateLiveEvent(parsed);
					if (!validated.ok) {
						args.onError?.(validated.error.detail);
						controller.abort();
						return;
					}
					args.onEvent(validated.event);
				}
			}
		} catch (error) {
			if (controller.signal.aborted) return;
			args.onError?.(error instanceof Error ? error.message : "SSE stream failed.");
		} finally {
			if (args.signal) args.signal.removeEventListener("abort", onAbort);
		}
	})();

	return {
		close: () => controller.abort(),
		done,
	};
}

export function contractAllowsLiveAdapterExecution(contract: BattleLiveTransportContractV1): boolean {
	return contract.transport.kind === "sse" && Boolean(contract.transport.endpoint) && Boolean(contract.initial_snapshot.endpoint);
}

/**
 * Live lane-event bus.
 *
 * `useBattleLiveTransport` owns the single EventSource for the `#battle/live`
 * route. Panes that also want the live frames (e.g. AgentDetailPane's streaming
 * stdout/stderr console + packet panel) subscribe here instead of opening a
 * second EventSource. Append-only, seq-deduped, cleared on stream (re)start.
 */
export type BattleLiveBusMeta = {
	/** Mirror of BattleLiveSseClientState.status (kept as a string to avoid a type cycle). */
	status: string;
	appliedSeq: number;
	lastSeq: number;
};

export type BattleLiveBusSnapshot = {
	events: BattleLiveEventV1[];
	meta: BattleLiveBusMeta;
};

const IDLE_LIVE_BUS_META: BattleLiveBusMeta = { status: "idle", appliedSeq: 0, lastSeq: 0 };

const liveBusEvents: BattleLiveEventV1[] = [];
let liveBusMeta: BattleLiveBusMeta = { ...IDLE_LIVE_BUS_META };
const liveBusListeners = new Set<(snapshot: BattleLiveBusSnapshot) => void>();

function liveBusSnapshot(): BattleLiveBusSnapshot {
	return { events: liveBusEvents.slice(), meta: liveBusMeta };
}

function emitLiveBus(): void {
	const snapshot = liveBusSnapshot();
	for (const listener of liveBusListeners) listener(snapshot);
}

/** Clear the bus when a fresh live stream starts (route change / reconnect / resume from 0). */
export function resetBattleLiveBus(): void {
	if (liveBusEvents.length === 0 && liveBusMeta.status === "idle") return;
	liveBusEvents.length = 0;
	liveBusMeta = { ...IDLE_LIVE_BUS_META };
	emitLiveBus();
}

/** Publish one validated live frame. Duplicates (by seq) are ignored; order kept ascending. */
export function publishBattleLiveEvent(event: BattleLiveEventV1): void {
	if (liveBusEvents.some((existing) => existing.seq === event.seq)) return;
	liveBusEvents.push(event);
	liveBusEvents.sort((a, b) => a.seq - b.seq);
	emitLiveBus();
}

/** Publish the current stream status so subscribers can render connecting/open/ended chrome. */
export function publishBattleLiveMeta(meta: BattleLiveBusMeta): void {
	if (liveBusMeta.status === meta.status && liveBusMeta.appliedSeq === meta.appliedSeq && liveBusMeta.lastSeq === meta.lastSeq) {
		return;
	}
	liveBusMeta = meta;
	emitLiveBus();
}

/** Subscribe to live frames + status. The listener is invoked immediately with the current snapshot. */
export function subscribeBattleLiveBus(listener: (snapshot: BattleLiveBusSnapshot) => void): () => void {
	liveBusListeners.add(listener);
	listener(liveBusSnapshot());
	return () => {
		liveBusListeners.delete(listener);
	};
}

export function currentBattleLiveBusSnapshot(): BattleLiveBusSnapshot {
	return liveBusSnapshot();
}
