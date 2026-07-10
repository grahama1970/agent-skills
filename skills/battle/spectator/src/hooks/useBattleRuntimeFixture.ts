import { useEffect, useState } from "react";
import { loadBattleRuntimeFixture } from "../lib/battle-runtime-loader";
import { isBattleRuntimeView } from "../lib/battle-runtime-registry";
import type { BattleNormalizedRuntimeJudgeFixtureV1, RuntimeLoadError } from "../lib/battle-runtime-types";
import { buildRuntimeViewModel, type RuntimeViewModel } from "../lib/battle-runtime-view-model";

export function useBattleRuntimeFixture() {
	const [routeKey, setRouteKey] = useState(() => (typeof window !== "undefined" ? window.location.hash : ""));
	const [viewModel, setViewModel] = useState<RuntimeViewModel | null>(null);
	const [fixture, setFixture] = useState<BattleNormalizedRuntimeJudgeFixtureV1 | null>(null);
	const [error, setError] = useState<RuntimeLoadError | null>(null);
	const [loading, setLoading] = useState(() => isBattleRuntimeView());

	useEffect(() => {
		const onHashChange = () => setRouteKey(window.location.hash);
		window.addEventListener("hashchange", onHashChange);
		return () => window.removeEventListener("hashchange", onHashChange);
	}, []);

	useEffect(() => {
		if (!isBattleRuntimeView(routeKey)) {
			setViewModel(null);
			setFixture(null);
			setError(null);
			setLoading(false);
			return;
		}

		let cancelled = false;
		setLoading(true);
		setError(null);

		loadBattleRuntimeFixture(routeKey).then((result) => {
			if (cancelled) return;
			if (!result.ok) {
				setFixture(null);
				setViewModel(null);
				setError(result.error);
				setLoading(false);
				return;
			}
			setFixture(result.fixture);
			setViewModel(buildRuntimeViewModel(result.fixture));
			setLoading(false);
		});

		return () => {
			cancelled = true;
		};
	}, [routeKey]);

	return {
		isRuntimeRoute: isBattleRuntimeView(routeKey),
		fixture,
		viewModel,
		error,
		loading,
	};
}
