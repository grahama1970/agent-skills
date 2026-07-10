import { useEffect, useState } from "react";
import type { BattleNormalizedUxFixture } from "../lib/battle-types";
import { battleReceiptReplayFixtureUrl, isBattleReceiptReplayView } from "../lib/battle-receipt-replay";
import { formatBattleFixtureLoadError, loadBattleRaceFixture } from "../lib/battle-view-fixture-loader";

export function useReceiptReplayFixture() {
	const [fixture, setFixture] = useState<BattleNormalizedUxFixture | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [loading, setLoading] = useState(() => isBattleReceiptReplayView());
	const [routeKey, setRouteKey] = useState(() => (typeof window !== "undefined" ? window.location.hash : ""));

	useEffect(() => {
		const onHashChange = () => setRouteKey(window.location.hash);
		window.addEventListener("hashchange", onHashChange);
		return () => window.removeEventListener("hashchange", onHashChange);
	}, []);

	useEffect(() => {
		if (!isBattleReceiptReplayView()) {
			setFixture(null);
			setError(null);
			setLoading(false);
			return;
		}

		let cancelled = false;
		setLoading(true);
		setError(null);

		loadBattleRaceFixture(battleReceiptReplayFixtureUrl(routeKey)).then((result) => {
			if (cancelled) return;
			if (!result.ok) {
				setFixture(null);
				setError(formatBattleFixtureLoadError(result.error));
				setLoading(false);
				return;
			}
			setFixture(result.fixture);
			setLoading(false);
		});

		return () => {
			cancelled = true;
		};
	}, [routeKey]);

	return {
		isReceiptRoute: isBattleReceiptReplayView(),
		fixture,
		error,
		loading,
	};
}
