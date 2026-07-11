import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { BattleScoreCueId } from "../lib/battle-music-catalog";
import { createBattleScoreRuntime, type BattleScoreRuntime } from "../lib/battle-score-runtime";

export function useBattleScore(getContext: () => AudioContext) {
	const runtimeRef = useRef<BattleScoreRuntime | null>(null);
	const [activeCueId, setActiveCueId] = useState<BattleScoreCueId | "motif" | "promoted" | null>(null);
	const [loopPlaying, setLoopPlaying] = useState(false);

	const ensure = useCallback(() => {
		if (!runtimeRef.current) {
			runtimeRef.current = createBattleScoreRuntime(getContext);
		}
		return runtimeRef.current;
	}, [getContext]);

	useEffect(() => () => runtimeRef.current?.stopAll(), []);

	const refresh = useCallback(() => {
		const rt = runtimeRef.current;
		if (!rt) return;
		setActiveCueId(rt.activeCueId());
		setLoopPlaying(rt.isLoopPlaying());
	}, []);

	const playCue = useCallback(
		async (cueId: BattleScoreCueId) => {
			const rt = ensure();
			rt.arm();
			await rt.playCue(cueId);
			refresh();
		},
		[ensure, refresh],
	);

	const playMotif = useCallback(
		async (spriteId: string) => {
			const rt = ensure();
			rt.arm();
			const ok = await rt.playMotif(spriteId);
			refresh();
			return ok;
		},
		[ensure, refresh],
	);

	const playPromotedUrl = useCallback(
		async (url: string, opts?: { loop?: boolean; asLoop?: boolean; label?: string; gain?: number }) => {
			const rt = ensure();
			rt.arm();
			await rt.playPromotedUrl(url, opts);
			refresh();
		},
		[ensure, refresh],
	);

	const startLoop = useCallback(async () => {
		await playCue("live_arena_loop");
	}, [playCue]);

	const stopAll = useCallback(() => {
		runtimeRef.current?.stopAll();
		refresh();
	}, [refresh]);

	return useMemo(
		() => ({
			provisionalGmRender: true as const,
			activeCueId,
			loopPlaying,
			playCue,
			playMotif,
			playPromotedUrl,
			startLoop,
			stopAll,
			ensure,
		}),
		[activeCueId, ensure, loopPlaying, playCue, playMotif, playPromotedUrl, startLoop, stopAll],
	);
}
