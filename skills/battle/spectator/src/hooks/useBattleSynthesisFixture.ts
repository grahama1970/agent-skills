import { useEffect, useState } from "react";
import { loadBattleSynthesisFixture } from "../lib/battle-synthesis-loader";
import { isBattleSynthesisView } from "../lib/battle-synthesis-registry";
import type { BattleNormalizedSynthesisFixtureV1, SynthesisLoadError } from "../lib/battle-synthesis-types";
import { buildSynthesisViewModel, type SynthesisViewModel } from "../lib/battle-synthesis-view-model";

export function useBattleSynthesisFixture() {
	const [routeKey, setRouteKey] = useState(() => (typeof window !== "undefined" ? window.location.hash : ""));
	const [viewModel, setViewModel] = useState<SynthesisViewModel | null>(null);
	const [fixture, setFixture] = useState<BattleNormalizedSynthesisFixtureV1 | null>(null);
	const [error, setError] = useState<SynthesisLoadError | null>(null);
	const [loading, setLoading] = useState(() => isBattleSynthesisView());

	useEffect(() => {
		const onHashChange = () => setRouteKey(window.location.hash);
		window.addEventListener("hashchange", onHashChange);
		return () => window.removeEventListener("hashchange", onHashChange);
	}, []);

	useEffect(() => {
		if (!isBattleSynthesisView(routeKey)) {
			setViewModel(null);
			setFixture(null);
			setError(null);
			setLoading(false);
			return;
		}

		let cancelled = false;
		setLoading(true);
		setError(null);

		loadBattleSynthesisFixture(routeKey).then((result) => {
			if (cancelled) return;
			if (!result.ok) {
				setFixture(null);
				setViewModel(null);
				setError(result.error);
				setLoading(false);
				return;
			}
			setFixture(result.fixture);
			setViewModel(buildSynthesisViewModel(result.fixture));
			setLoading(false);
		});

		return () => {
			cancelled = true;
		};
	}, [routeKey]);

	return {
		isSynthesisRoute: isBattleSynthesisView(routeKey),
		fixture,
		viewModel,
		error,
		loading,
	};
}
