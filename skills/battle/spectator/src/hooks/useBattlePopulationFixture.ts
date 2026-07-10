import { useEffect, useState } from "react";
import { loadBattlePopulationFixture } from "../lib/battle-population-loader";
import { isBattlePopulationView } from "../lib/battle-population-registry";
import type { BattleNormalizedPopulationFixtureV1, PopulationLoadError } from "../lib/battle-population-types";
import { buildPopulationViewModel, type PopulationViewModel } from "../lib/battle-population-view-model";

export function useBattlePopulationFixture() {
	const [routeKey, setRouteKey] = useState(() => (typeof window !== "undefined" ? window.location.hash : ""));
	const [selectedGeneration, setSelectedGeneration] = useState<number | null>(null);
	const [fixture, setFixture] = useState<BattleNormalizedPopulationFixtureV1 | null>(null);
	const [error, setError] = useState<PopulationLoadError | null>(null);
	const [loading, setLoading] = useState(() => isBattlePopulationView());

	useEffect(() => {
		const onHashChange = () => setRouteKey(window.location.hash);
		window.addEventListener("hashchange", onHashChange);
		return () => window.removeEventListener("hashchange", onHashChange);
	}, []);

	useEffect(() => {
		if (!isBattlePopulationView(routeKey)) {
			setFixture(null);
			setError(null);
			setLoading(false);
			return;
		}

		let cancelled = false;
		setLoading(true);
		setError(null);

		loadBattlePopulationFixture(routeKey).then((result) => {
			if (cancelled) return;
			if (!result.ok) {
				setFixture(null);
				setError(result.error);
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

	const viewModel: PopulationViewModel | null = fixture ? buildPopulationViewModel(fixture, selectedGeneration) : null;

	return {
		isPopulationRoute: isBattlePopulationView(routeKey),
		fixture,
		viewModel,
		error,
		loading,
		selectedGeneration,
		setSelectedGeneration,
	};
}
