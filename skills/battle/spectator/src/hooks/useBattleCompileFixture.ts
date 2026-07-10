import { useEffect, useState } from "react";
import { loadBattleCompileFixture } from "../lib/battle-compile-loader";
import { isBattleCompileView } from "../lib/battle-compile-registry";
import type { BattleNormalizedCompileFixtureV1, CompileLoadError } from "../lib/battle-compile-types";
import { buildCompileViewModel, type CompileViewModel } from "../lib/battle-compile-view-model";

export function useBattleCompileFixture() {
	const [routeKey, setRouteKey] = useState(() => (typeof window !== "undefined" ? window.location.hash : ""));
	const [viewModel, setViewModel] = useState<CompileViewModel | null>(null);
	const [fixture, setFixture] = useState<BattleNormalizedCompileFixtureV1 | null>(null);
	const [error, setError] = useState<CompileLoadError | null>(null);
	const [loading, setLoading] = useState(() => isBattleCompileView());

	useEffect(() => {
		const onHashChange = () => setRouteKey(window.location.hash);
		window.addEventListener("hashchange", onHashChange);
		return () => window.removeEventListener("hashchange", onHashChange);
	}, []);

	useEffect(() => {
		if (!isBattleCompileView(routeKey)) {
			setViewModel(null);
			setFixture(null);
			setError(null);
			setLoading(false);
			return;
		}

		let cancelled = false;
		setLoading(true);
		setError(null);

		loadBattleCompileFixture(routeKey).then((result) => {
			if (cancelled) return;
			if (!result.ok) {
				setFixture(null);
				setViewModel(null);
				setError(result.error);
				setLoading(false);
				return;
			}
			setFixture(result.fixture);
			setViewModel(buildCompileViewModel(result.fixture));
			setLoading(false);
		});

		return () => {
			cancelled = true;
		};
	}, [routeKey]);

	return {
		isCompileRoute: isBattleCompileView(routeKey),
		fixture,
		viewModel,
		error,
		loading,
	};
}
