import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
	battleLiveTransportBattleId,
	battleLiveTransportFixtureKey,
	battleLiveTransportMode,
	battleLiveRuntimeTransport,
	isBattleLiveView,
} from "../lib/battle-transport-registry";
import { loadBattleTransportPackage } from "../lib/battle-transport-loader";
import { loadBattleLiveTransportContract } from "../lib/battle-live-transport-contract-loader";
import {
	createIdleLiveSseClientState,
	planLiveSseClient,
	planLiveWebSocketClient,
	applySseLiveEvent,
	shouldOpenEventSource,
	shouldOpenWebSocket,
	type BattleLiveSseClientState,
} from "../lib/battle-live-sse-client";
import {
	buildLiveSseTransportPackage,
	buildLiveWebSocketTransportPackage,
	contractAllowsLiveAdapterExecution,
	discoverBattleLiveTransportAdapter,
	fetchBattleLiveSnapshot,
	openBattleLiveSseStream,
	openBattleLiveWebSocketStream,
	resolveBattleLiveTransportBaseUrl,
} from "../lib/battle-live-sse-runtime";
import { battleLiveTransportContractCompanionUrl } from "../lib/battle-live-transport-contract-registry";
import {
	bootstrapLiveTransportState,
	bootstrapTransportState,
	createIdleTransportState,
	recoverTransportFromPackage,
	setTransportCursorSeconds,
	setTransportFollowLive,
	transportViewModel,
	type BattleTransportState,
} from "../lib/battle-transport-reducer";
import type { BattleNormalizedUxFixture } from "../lib/battle-types";
import type { BattleTransportLoadError, BattleTransportViewModel } from "../lib/battle-transport-types";
import type {
	BattleLiveTransportContractLoadError,
	BattleLiveTransportContractV1,
	BattleLiveTransportContractViewModel,
} from "../lib/battle-live-transport-contract-types";

export function useBattleLiveTransport() {
	const [routeEpoch, setRouteEpoch] = useState(0);
	useEffect(() => {
		const onHashChange = () => setRouteEpoch((value) => value + 1);
		window.addEventListener("hashchange", onHashChange);
		return () => window.removeEventListener("hashchange", onHashChange);
	}, []);

	const isLiveRoute = isBattleLiveView();
	const mode = battleLiveTransportMode();
	const runtimeTransport = battleLiveRuntimeTransport();
	const fixtureKey = battleLiveTransportFixtureKey();
	const battleId = battleLiveTransportBattleId();
	const liveBaseUrl = resolveBattleLiveTransportBaseUrl();
	const routeKey = `${routeEpoch}:${mode}:${runtimeTransport}:${fixtureKey ?? ""}:${battleId ?? ""}:${liveBaseUrl}`;

	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<BattleTransportLoadError | BattleLiveTransportContractLoadError | null>(null);
	const [companion, setCompanion] = useState<BattleNormalizedUxFixture | null>(null);
	const [state, setState] = useState<BattleTransportState>(createIdleTransportState);
	const [contract, setContract] = useState<BattleLiveTransportContractV1 | null>(null);
	const [contractModel, setContractModel] = useState<BattleLiveTransportContractViewModel | null>(null);
	const [sseClient, setSseClient] = useState<BattleLiveSseClientState>(createIdleLiveSseClientState);
	const streamCloseRef = useRef<(() => void) | null>(null);

	const stopStream = useCallback(() => {
		streamCloseRef.current?.();
		streamCloseRef.current = null;
	}, []);

	const startLiveSse = useCallback(
		async (args: {
			contract: BattleLiveTransportContractV1;
			companion: BattleNormalizedUxFixture;
			baseUrl: string;
			lastEventId?: number;
		}) => {
			stopStream();
			const snapshotResult = await fetchBattleLiveSnapshot({
				baseUrl: args.baseUrl,
				snapshotEndpoint: args.contract.initial_snapshot.endpoint,
			});
			if (!snapshotResult.ok) {
				setError(snapshotResult.error);
				setSseClient({
					status: "error",
					lastSeq: 0,
					lastEventId: null,
					error: snapshotResult.error.detail,
					endpoint: args.contract.transport.endpoint,
					baseUrl: args.baseUrl,
					live: "local_http_sse_adapter",
					transportMode: (args.lastEventId ?? 0) > 0 ? "fetch_last_event_id" : "event_source",
				});
				return;
			}

			const pack = buildLiveSseTransportPackage({
				snapshot: snapshotResult.snapshot,
				baseUrl: args.baseUrl,
				companionFixtureUrl: battleLiveTransportContractCompanionUrl(
					args.contract.battle_id as "battle-004",
				),
			});
			setError(null);
			setCompanion(args.companion);
			setState(bootstrapLiveTransportState(pack));
			const transportMode = (args.lastEventId ?? 0) > 0 ? "fetch_last_event_id" : "event_source";
			setSseClient({
				status: "connecting",
				lastSeq: 0,
				lastEventId: args.lastEventId != null ? String(args.lastEventId) : null,
				error: null,
				endpoint: args.contract.transport.endpoint,
				baseUrl: args.baseUrl,
				live: "local_http_sse_adapter",
				transportMode,
			});

			const handle = openBattleLiveSseStream({
				baseUrl: args.baseUrl,
				eventsEndpoint: args.contract.transport.endpoint,
				lastEventId: args.lastEventId ?? 0,
				onOpen: () => {
					setSseClient((current) => ({
						...current,
						status: "open",
						transportMode,
						error: null,
					}));
				},
				onEvent: (event) => {
					setState((current) => {
						const next = applySseLiveEvent(current, event);
						const lastSeq = next.pack?.manifest.last_seq ?? 0;
						if (event.seq >= lastSeq && lastSeq > 0) {
							// Finite adapter stream complete — close EventSource to avoid reconnect loop.
							queueMicrotask(() => streamCloseRef.current?.());
						}
						return next;
					});
					setSseClient((current) => ({
						...current,
						status: "open",
						lastSeq: event.seq,
						lastEventId: String(event.seq),
						transportMode,
						error: null,
					}));
				},
				onError: (message) => {
					setSseClient((current) => ({
						...current,
						status: "error",
						error: message,
					}));
					setState((current) =>
						current.status === "gap_recovery"
							? current
							: {
									...current,
									status: "error",
									error: message,
									followLive: false,
								},
					);
				},
			});
			streamCloseRef.current = handle.close;
			void handle.done.then(() => {
				setSseClient((current) =>
					current.status === "error" || current.status === "gap_recovery"
						? current
						: {
								...current,
								status: "ended",
							},
				);
			});
		},
		[stopStream],
	);

	const startLiveWebSocket = useCallback(
		async (args: {
			contract: BattleLiveTransportContractV1;
			companion: BattleNormalizedUxFixture;
			baseUrl: string;
			webSocketPort: number;
		}) => {
			stopStream();
			const endpoint = args.contract.websocket?.endpoint ?? null;
			if (!endpoint) {
				setError({
					code: "CONTRACT_VALIDATION_FAILED",
					title: "CONTRACT VALIDATION FAILED",
					detail: "Contract does not advertise a WebSocket endpoint.",
				});
				setSseClient(planLiveWebSocketClient(args.contract, { adapterAvailable: false, baseUrl: args.baseUrl }));
				return;
			}
			setError(null);
			setCompanion(args.companion);
			setSseClient({
				status: "connecting",
				lastSeq: 0,
				lastEventId: null,
				error: null,
				endpoint,
				baseUrl: args.baseUrl,
				live: "local_http_websocket_adapter",
				transportMode: "websocket",
			});
			let expectedLastSeq = 0;
			const handle = openBattleLiveWebSocketStream({
				baseUrl: args.baseUrl,
				webSocketEndpoint: endpoint,
				webSocketPort: args.webSocketPort,
				onOpen: () => {
					setSseClient((current) => ({
						...current,
						status: "open",
						transportMode: "websocket",
						error: null,
					}));
				},
				onSnapshot: (snapshot) => {
					expectedLastSeq = snapshot.last_seq;
					const pack = buildLiveWebSocketTransportPackage({
						snapshot,
						baseUrl: args.baseUrl,
						companionFixtureUrl: battleLiveTransportContractCompanionUrl(args.contract.battle_id as "battle-004"),
					});
					setState(bootstrapLiveTransportState(pack));
				},
				onEvent: (event) => {
					setState((current) => {
						const next = applySseLiveEvent(current, event);
						const lastSeq = next.pack?.manifest.last_seq ?? expectedLastSeq;
						if (event.seq >= lastSeq && lastSeq > 0) {
							queueMicrotask(() => streamCloseRef.current?.());
						}
						return next;
					});
					setSseClient((current) => ({
						...current,
						status: "open",
						lastSeq: event.seq,
						lastEventId: String(event.seq),
						transportMode: "websocket",
						error: null,
					}));
				},
				onError: (message) => {
					setSseClient((current) => ({
						...current,
						status: "error",
						error: message,
					}));
					setState((current) =>
						current.status === "gap_recovery"
							? current
							: {
									...current,
									status: "error",
									error: message,
									followLive: false,
								},
					);
				},
			});
			streamCloseRef.current = handle.close;
			void handle.done.then(() => {
				setSseClient((current) =>
					current.status === "error" || current.status === "gap_recovery"
						? current
						: {
								...current,
								status: "ended",
							},
				);
			});
		},
		[stopStream],
	);

	useEffect(() => {
		if (!isLiveRoute) {
			stopStream();
			setLoading(false);
			setError(null);
			setCompanion(null);
			setState(createIdleTransportState());
			setContract(null);
			setContractModel(null);
			setSseClient(createIdleLiveSseClientState());
			return;
		}

		let cancelled = false;
		setLoading(true);
		setError(null);
		stopStream();

		async function load() {
			if (mode === "contract" && battleId) {
				const result = await loadBattleLiveTransportContract(battleId);
				if (cancelled) return;
				if (!result.ok) {
					setLoading(false);
					setError(result.error);
					setCompanion(null);
					setContract(null);
					setContractModel(null);
					setState(createIdleTransportState());
					setSseClient(createIdleLiveSseClientState());
					return;
				}

				setContract(result.contract);
				setContractModel(result.viewModel);
				setCompanion(result.companion);

				const canExecute = contractAllowsLiveAdapterExecution(result.contract);
				// Stay contract_only_blocked unless serve-live-transport healthz PASS.
				const probe = canExecute
					? await discoverBattleLiveTransportAdapter({ battleId })
					: ({
							ok: false as const,
							error: {
								code: "TRANSPORT_UNAVAILABLE" as const,
								title: "TRANSPORT UNAVAILABLE",
								detail: "Contract transport incomplete.",
							},
					  });

				if (cancelled) return;

				if (
					runtimeTransport === "websocket" &&
					probe.ok &&
					shouldOpenWebSocket(result.contract, {
						adapterAvailable: true,
						websocketAvailable:
							probe.webSocketEndpoint === result.contract.websocket?.endpoint && probe.webSocketPort != null,
					})
				) {
					const webSocketPort = probe.webSocketPort;
					if (webSocketPort == null) return;
					setLoading(false);
					setSseClient(
						planLiveWebSocketClient(result.contract, {
							adapterAvailable: true,
							baseUrl: probe.baseUrl,
						}),
					);
					await startLiveWebSocket({
						contract: result.contract,
						companion: result.companion,
						baseUrl: probe.baseUrl,
						webSocketPort,
					});
					return;
				}

				if (runtimeTransport === "sse" && probe.ok && shouldOpenEventSource(result.contract, { adapterAvailable: true })) {
					setLoading(false);
					setSseClient(
						planLiveSseClient(result.contract, {
							adapterAvailable: true,
							baseUrl: probe.baseUrl,
						}),
					);
					await startLiveSse({
						contract: result.contract,
						companion: result.companion,
						baseUrl: probe.baseUrl,
					});
					return;
				}

				setLoading(false);
				setState(createIdleTransportState());
				setSseClient(
					runtimeTransport === "websocket"
						? planLiveWebSocketClient(result.contract, {
								adapterAvailable: false,
								baseUrl: liveBaseUrl,
							})
						: planLiveSseClient(result.contract, {
								adapterAvailable: false,
								baseUrl: liveBaseUrl,
							}),
				);
				return;
			}

			if (mode === "file_backed" && fixtureKey) {
				const result = await loadBattleTransportPackage(fixtureKey);
				if (cancelled) return;
				setLoading(false);
				if (!result.ok) {
					setError(result.error);
					setCompanion(null);
					setState(createIdleTransportState());
					setContract(null);
					setContractModel(null);
					setSseClient(createIdleLiveSseClientState());
					return;
				}
				setError(null);
				setCompanion(result.companion);
				setState(bootstrapTransportState(result.pack));
				setContract(null);
				setContractModel(null);
				setSseClient(createIdleLiveSseClientState());
				return;
			}

			setLoading(false);
			setCompanion(null);
			setState(createIdleTransportState());
			setContract(null);
			setContractModel(null);
			setSseClient(createIdleLiveSseClientState());
			setError({
				code: "UNSUPPORTED_FIXTURE",
				title: "UNSUPPORTED LIVE ROUTE",
				detail: "Provide ?battle=battle-004 (contract) or a registered ?fixture= stream key.",
			});
		}

		void load();
		return () => {
			cancelled = true;
			stopStream();
		};
	}, [battleId, fixtureKey, isLiveRoute, liveBaseUrl, mode, routeKey, runtimeTransport, startLiveSse, startLiveWebSocket, stopStream]);

	// Reflect reducer gap state onto SSE client chrome.
	useEffect(() => {
		if (state.status === "gap_recovery") {
			setSseClient((current) => ({
				...current,
				status: "gap_recovery",
				error: state.error,
			}));
		}
	}, [state.error, state.status]);

	const model: BattleTransportViewModel | null = useMemo(() => transportViewModel(state), [state]);

	const returnToLive = useCallback(() => {
		setState((current) => setTransportFollowLive(current, true));
	}, []);

	const scrubToSeconds = useCallback((seconds: number) => {
		setState((current) => setTransportCursorSeconds(current, seconds));
	}, []);

	const recoverFromGap = useCallback(async () => {
		if (!isLiveRoute) return;
		if (mode === "file_backed" && fixtureKey) {
			setLoading(true);
			const result = await loadBattleTransportPackage(fixtureKey);
			setLoading(false);
			if (!result.ok) {
				setError(result.error);
				return;
			}
			setError(null);
			setCompanion(result.companion);
			setState(recoverTransportFromPackage(result.pack));
			return;
		}
		if (mode === "contract" && contract && companion && sseClient.baseUrl) {
			setLoading(true);
			if (sseClient.transportMode === "websocket") {
				const probe = await discoverBattleLiveTransportAdapter({ battleId: contract.battle_id });
				if (probe.ok && probe.webSocketPort != null) {
					await startLiveWebSocket({
						contract,
						companion,
						baseUrl: probe.baseUrl,
						webSocketPort: probe.webSocketPort,
					});
				}
			} else {
				await startLiveSse({
					contract,
					companion,
					baseUrl: sseClient.baseUrl,
					lastEventId: 0,
				});
			}
			setLoading(false);
		}
	}, [companion, contract, fixtureKey, isLiveRoute, mode, sseClient.baseUrl, sseClient.transportMode, startLiveSse, startLiveWebSocket]);

	return {
		isLiveRoute,
		mode,
		runtimeTransport,
		fixtureKey,
		battleId,
		liveBaseUrl,
		loading,
		error,
		companion,
		state,
		model,
		contract,
		contractModel,
		sseClient,
		returnToLive,
		scrubToSeconds,
		recoverFromGap,
	};
}
