import { useEffect, useState } from "react";
import { loadBattleMusicFixture } from "../lib/battle-music-loader";
import { isBattleMusicView } from "../lib/battle-music-registry";
import type { BattleNormalizedMusicFixture, MusicFixtureLoadError, MusicScheduleViewModel } from "../lib/battle-normalized-music-fixture";

export function useBattleMusicFixture() {
	const [routeKey, setRouteKey] = useState(() => (typeof window !== "undefined" ? window.location.hash : ""));
	const [viewModel, setViewModel] = useState<MusicScheduleViewModel | null>(null);
	const [fixture, setFixture] = useState<BattleNormalizedMusicFixture | null>(null);
	const [error, setError] = useState<MusicFixtureLoadError | null>(null);
	const [loading, setLoading] = useState(() => isBattleMusicView());

	useEffect(() => {
		const onHashChange = () => setRouteKey(window.location.hash);
		window.addEventListener("hashchange", onHashChange);
		return () => window.removeEventListener("hashchange", onHashChange);
	}, []);

	useEffect(() => {
		if (!isBattleMusicView(routeKey)) {
			setViewModel(null);
			setFixture(null);
			setError(null);
			setLoading(false);
			return;
		}
		let cancelled = false;
		setLoading(true);
		setError(null);
		loadBattleMusicFixture(routeKey).then((result) => {
			if (cancelled) return;
			if (!result.ok) {
				setFixture(null);
				setViewModel(null);
				setError(result.error);
				setLoading(false);
				return;
			}
			setFixture(result.fixture);
			setViewModel(result.viewModel);
			setLoading(false);
		});
		return () => {
			cancelled = true;
		};
	}, [routeKey]);

	return {
		isMusicRoute: isBattleMusicView(routeKey),
		fixture,
		viewModel,
		error,
		loading,
	};
}
