import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
	battleLiveTransportBattleId,
	battleLiveTransportFixtureKey,
	battleLiveTransportMode,
	isBattleLiveView,
} from "../lib/battle-transport-registry";
import { loadBattleTransportPackage } from "../lib/battle-transport-loader";
import { loadBattleLiveTransportContract } from "../lib/battle-live-transport-contract-loader";
import {
	createIdleLiveSseClientState,
	planLiveSseClient,
	applySseLiveEvent,
	shouldOpenEventSource,
	type BattleLiveSseClientState,
} from "../lib/battle-live-sse-client";
import {
	buildLiveSseTransportPackage,
	contractAllowsLiveAdapterExecution,
	discoverBattleLiveTransportAdapter,
	fetchBattleLiveSnapshot,
	openBattleLiveSseStream,
	publishBattleLiveEvent,
	publishBattleLiveMeta,
	resetBattleLiveBus,
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
	const fixtureKey = battleLiveTransportFixtureKey();
	const battleId = battleLiveTransportBattleId();
	const liveBaseUrl = resolveBattleLiveTransportBaseUrl();
	const routeKey = `${routeEpoch}:${mode}:${fixtureKey ?? ""}:${battleId ?? ""}:${liveBaseUrl}`;

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
			// Fresh connect (not a Last-Event-ID resume) clears the shared lane-event bus.
			if ((args.lastEventId ?? 0) === 0) resetBattleLiveBus();
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
					// Fan out to panes (AgentDetailPane streaming console/packet panel) via the shared bus.
					publishBattleLiveEvent(event);
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

	useEffect(() => {
		if (!isLiveRoute) {
			stopStream();
			resetBattleLiveBus();
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

				if (probe.ok && shouldOpenEventSource(result.contract, { adapterAvailable: true })) {
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
					planLiveSseClient(result.contract, {
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
	}, [battleId, fixtureKey, isLiveRoute, liveBaseUrl, mode, routeKey, startLiveSse, stopStream]);

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

	// Mirror live stream status onto the shared bus so subscribed panes render connecting/open/ended.
	useEffect(() => {
		if (!isLiveRoute) return;
		publishBattleLiveMeta({
			status: sseClient.status,
			appliedSeq: model?.appliedSeq ?? 0,
			lastSeq: model?.lastSeq ?? 0,
		});
	}, [isLiveRoute, sseClient.status, model?.appliedSeq, model?.lastSeq]);

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
			await startLiveSse({
				contract,
				companion,
				baseUrl: sseClient.baseUrl,
				lastEventId: 0,
			});
			setLoading(false);
		}
	}, [companion, contract, fixtureKey, isLiveRoute, mode, sseClient.baseUrl, startLiveSse]);

	return {
		isLiveRoute,
		mode,
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
