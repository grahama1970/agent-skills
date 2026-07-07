import { useEffect, useRef } from "react";
import type { BattleEffectCue, BattleEvent, BattleNormalizedUxFixture, Lane } from "../lib/battle-types";
import { collectReplayCueCrossings } from "../lib/battle-replay-cues";

export function useBattleReplayCues(args: {
	playheadSeconds: number;
	fixture: BattleNormalizedUxFixture;
	lanes: Lane[];
	battleEvents: BattleEvent[];
	enabled: boolean;
	onCue?: (cue: BattleEffectCue) => void;
}) {
	const { playheadSeconds, fixture, lanes, battleEvents, enabled, onCue } = args;
	const lastSecondsRef = useRef(playheadSeconds);
	const firedRef = useRef<Set<string>>(new Set());

	useEffect(() => {
		lastSecondsRef.current = playheadSeconds;
	}, []);

	useEffect(() => {
		if (!enabled || !onCue) return;

		const prevSeconds = lastSecondsRef.current;
		if (playheadSeconds + 0.0001 < prevSeconds) {
			for (const id of [...firedRef.current]) {
				const at = Number(id.split("@")[1]);
				if (!Number.isNaN(at) && at > playheadSeconds) firedRef.current.delete(id);
			}
		}

		const crossings = collectReplayCueCrossings({
			prevSeconds,
			nextSeconds: playheadSeconds,
			fixture,
			lanes,
			battleEvents,
		});

		for (const cue of crossings) {
			const token = `${cue.eventId}@${cue.atSeconds.toFixed(3)}`;
			if (firedRef.current.has(token)) continue;
			firedRef.current.add(token);
			onCue(cue);
		}

		lastSecondsRef.current = playheadSeconds;
	}, [battleEvents, enabled, fixture, lanes, onCue, playheadSeconds]);
}
