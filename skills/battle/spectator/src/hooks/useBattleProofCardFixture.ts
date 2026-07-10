import { useEffect, useState } from "react";
import { loadBattleProofCardFixture } from "../lib/battle-proof-card-loader";
import { isBattleProofCardView } from "../lib/battle-proof-card-registry";
import type { BattleNormalizedProofCardFixtureV1, ProofCardLoadError } from "../lib/battle-proof-card-types";
import { buildProofCardViewModel, type ProofCardViewModel } from "../lib/battle-proof-card-view-model";

export function useBattleProofCardFixture() {
	const [routeKey, setRouteKey] = useState(() => (typeof window !== "undefined" ? window.location.hash : ""));
	const [viewModel, setViewModel] = useState<ProofCardViewModel | null>(null);
	const [fixture, setFixture] = useState<BattleNormalizedProofCardFixtureV1 | null>(null);
	const [error, setError] = useState<ProofCardLoadError | null>(null);
	const [loading, setLoading] = useState(() => isBattleProofCardView());

	useEffect(() => {
		const onHashChange = () => setRouteKey(window.location.hash);
		window.addEventListener("hashchange", onHashChange);
		return () => window.removeEventListener("hashchange", onHashChange);
	}, []);

	useEffect(() => {
		if (!isBattleProofCardView(routeKey)) {
			setViewModel(null);
			setFixture(null);
			setError(null);
			setLoading(false);
			return;
		}

		let cancelled = false;
		setLoading(true);
		setError(null);

		loadBattleProofCardFixture(routeKey).then((result) => {
			if (cancelled) return;
			if (!result.ok) {
				setFixture(null);
				setViewModel(null);
				setError(result.error);
				setLoading(false);
				return;
			}
			setFixture(result.fixture);
			setViewModel(buildProofCardViewModel(result.fixture));
			setLoading(false);
		});

		return () => {
			cancelled = true;
		};
	}, [routeKey]);

	return {
		isProofCardRoute: isBattleProofCardView(routeKey),
		fixture,
		viewModel,
		error,
		loading,
	};
}
