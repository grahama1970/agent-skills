import { useCallback, useEffect, useMemo, useState } from "react";
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
	type BattleLiveSseClientState,
} from "../lib/battle-live-sse-client";
import {
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
	const routeKey = `${routeEpoch}:${mode}:${fixtureKey ?? ""}:${battleId ?? ""}`;

	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<BattleTransportLoadError | BattleLiveTransportContractLoadError | null>(null);
	const [companion, setCompanion] = useState<BattleNormalizedUxFixture | null>(null);
	const [state, setState] = useState<BattleTransportState>(createIdleTransportState);
	const [contract, setContract] = useState<BattleLiveTransportContractV1 | null>(null);
	const [contractModel, setContractModel] = useState<BattleLiveTransportContractViewModel | null>(null);
	const [sseClient, setSseClient] = useState<BattleLiveSseClientState>(createIdleLiveSseClientState);

	useEffect(() => {
		if (!isLiveRoute) {
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

		async function load() {
			if (mode === "contract" && battleId) {
				const result = await loadBattleLiveTransportContract(battleId);
				if (cancelled) return;
				setLoading(false);
				if (!result.ok) {
					setError(result.error);
					setCompanion(null);
					setContract(null);
					setContractModel(null);
					setState(createIdleTransportState());
					setSseClient(createIdleLiveSseClientState());
					return;
				}
				setError(null);
				setContract(result.contract);
				setContractModel(result.viewModel);
				setCompanion(result.companion);
				setState(createIdleTransportState());
				setSseClient(planLiveSseClient(result.contract));
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
		};
	}, [battleId, fixtureKey, isLiveRoute, mode, routeKey]);

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
		}
	}, [fixtureKey, isLiveRoute, mode]);

	return {
		isLiveRoute,
		mode,
		fixtureKey,
		battleId,
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
