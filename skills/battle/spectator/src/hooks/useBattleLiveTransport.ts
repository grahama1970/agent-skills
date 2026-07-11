import { useCallback, useEffect, useMemo, useState } from "react";
import {
	battleLiveTransportFixtureKey,
	isBattleLiveView,
} from "../lib/battle-transport-registry";
import { loadBattleTransportPackage } from "../lib/battle-transport-loader";
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

export function useBattleLiveTransport() {
	const [routeEpoch, setRouteEpoch] = useState(0);
	useEffect(() => {
		const onHashChange = () => setRouteEpoch((value) => value + 1);
		window.addEventListener("hashchange", onHashChange);
		return () => window.removeEventListener("hashchange", onHashChange);
	}, []);

	const isLiveRoute = isBattleLiveView();
	const fixtureKey = battleLiveTransportFixtureKey();
	const routeKey = `${routeEpoch}:${fixtureKey ?? "unsupported"}`;

	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<BattleTransportLoadError | null>(null);
	const [companion, setCompanion] = useState<BattleNormalizedUxFixture | null>(null);
	const [state, setState] = useState<BattleTransportState>(createIdleTransportState);

	useEffect(() => {
		if (!isLiveRoute) {
			setLoading(false);
			setError(null);
			setCompanion(null);
			setState(createIdleTransportState());
			return;
		}
		if (!fixtureKey) {
			setLoading(false);
			setCompanion(null);
			setState(createIdleTransportState());
			setError({
				code: "UNSUPPORTED_FIXTURE",
				title: "UNSUPPORTED FIXTURE",
				detail: "The requested live transport fixture is not registered.",
			});
			return;
		}
		let cancelled = false;
		setLoading(true);
		setError(null);
		loadBattleTransportPackage(fixtureKey).then((result) => {
			if (cancelled) return;
			setLoading(false);
			if (!result.ok) {
				setError(result.error);
				setCompanion(null);
				setState(createIdleTransportState());
				return;
			}
			setError(null);
			setCompanion(result.companion);
			setState(bootstrapTransportState(result.pack));
		});
		return () => {
			cancelled = true;
		};
	}, [fixtureKey, isLiveRoute, routeKey]);

	const model: BattleTransportViewModel | null = useMemo(() => transportViewModel(state), [state]);

	const returnToLive = useCallback(() => {
		setState((current) => setTransportFollowLive(current, true));
	}, []);

	const scrubToSeconds = useCallback((seconds: number) => {
		setState((current) => setTransportCursorSeconds(current, seconds));
	}, []);

	const recoverFromGap = useCallback(async () => {
		if (!isLiveRoute || !fixtureKey) return;
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
	}, [fixtureKey, isLiveRoute]);

	return {
		isLiveRoute,
		fixtureKey,
		loading,
		error,
		companion,
		state,
		model,
		returnToLive,
		scrubToSeconds,
		recoverFromGap,
	};
}
