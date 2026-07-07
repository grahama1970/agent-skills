import { useEffect, useState } from "react";
import type { BattleNormalizedUxFixture } from "../lib/battle-types";
import { BATTLE_RECEIPT_REPLAY_FIXTURE_URL, isBattleReceiptReplayView } from "../lib/battle-receipt-replay";

export function useReceiptReplayFixture() {
	const [fixture, setFixture] = useState<BattleNormalizedUxFixture | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [loading, setLoading] = useState(() => isBattleReceiptReplayView());
	const routeKey = typeof window !== "undefined" ? window.location.hash : "";

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

		fetch(BATTLE_RECEIPT_REPLAY_FIXTURE_URL)
			.then((response) => {
				if (!response.ok) throw new Error(`fixture fetch failed: HTTP ${response.status}`);
				return response.json() as Promise<BattleNormalizedUxFixture>;
			})
			.then((data) => {
				if (cancelled) return;
				setFixture(data);
				setLoading(false);
			})
			.catch((fetchError: unknown) => {
				if (cancelled) return;
				setFixture(null);
				setError(fetchError instanceof Error ? fetchError.message : String(fetchError));
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
