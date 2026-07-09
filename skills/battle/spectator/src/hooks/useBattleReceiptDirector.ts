import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { BattleNormalizedUxFixture, Lane } from "../lib/battle-types";
import {
	collectReceiptBeatCrossings,
	collectReceiptBeats,
	heroReceiptBeats,
	highlightReelPreRollSeconds,
	nextReceiptBeat,
	receiptBeatToEffectCue,
	type ReceiptBeat,
} from "../lib/battle-receipt-beats";

export type ReceiptDirectorHandlers = {
	onBeat?: (beat: ReceiptBeat) => void;
	onReactBeat?: (beat: ReceiptBeat) => void;
	onPixiBeat?: (beat: ReceiptBeat) => void;
	focusCamera?: (beat: ReceiptBeat, behavior?: ScrollBehavior) => void;
};

export function useBattleReceiptDirector(args: {
	fixture: BattleNormalizedUxFixture;
	lanes: Lane[];
	playheadSeconds: number;
	enabled: boolean;
	handlers: ReceiptDirectorHandlers;
}) {
	const { fixture, lanes, playheadSeconds, enabled, handlers } = args;
	const handlersRef = useRef(handlers);
	handlersRef.current = handlers;
	const beats = useMemo(() => collectReceiptBeats(fixture, lanes), [fixture, lanes]);
	const heroBeats = useMemo(() => heroReceiptBeats(beats), [beats]);
	const lastSecondsRef = useRef(playheadSeconds);
	const firedRef = useRef<Set<string>>(new Set());
	const [cameraFollow, setCameraFollow] = useState(true);
	const [activeBeat, setActiveBeat] = useState<ReceiptBeat | null>(null);

	useEffect(() => {
		lastSecondsRef.current = playheadSeconds;
	}, []);

	const dispatchBeat = useCallback(
		(beat: ReceiptBeat, behavior: ScrollBehavior = "smooth") => {
			setActiveBeat(beat);
			handlersRef.current.onBeat?.(beat);
			handlersRef.current.onReactBeat?.(beat);
			handlersRef.current.onPixiBeat?.(beat);
			if (beat.camera.follow && cameraFollow) handlersRef.current.focusCamera?.(beat, behavior);
		},
		[cameraFollow],
	);

	useEffect(() => {
		if (!enabled) return;
		const prevSeconds = lastSecondsRef.current;
		if (playheadSeconds + 0.0001 < prevSeconds) {
			for (const id of [...firedRef.current]) {
				const at = Number(id.split("@")[1]);
				if (!Number.isNaN(at) && at > playheadSeconds) firedRef.current.delete(id);
			}
		}
		const crossings = collectReceiptBeatCrossings({ prevSeconds, nextSeconds: playheadSeconds, beats });
		for (const beat of crossings) {
			const token = `${beat.id}@${beat.atSeconds.toFixed(3)}`;
			if (firedRef.current.has(token)) continue;
			firedRef.current.add(token);
			dispatchBeat(beat, "auto");
		}
		lastSecondsRef.current = playheadSeconds;
	}, [beats, dispatchBeat, enabled, playheadSeconds]);

	const pauseCameraFollow = useCallback(() => setCameraFollow(false), []);
	const resumeCameraFollow = useCallback(() => setCameraFollow(true), []);

	const jumpToNextHighlight = useCallback(
		(currentSeconds: number) => {
			const beat = nextReceiptBeat(heroBeats, currentSeconds);
			if (!beat) return null;
			dispatchBeat(beat, "smooth");
			return { beat, preRollSeconds: highlightReelPreRollSeconds(beat) };
		},
		[dispatchBeat, heroBeats],
	);

	return {
		beats,
		heroBeats,
		activeBeat,
		cameraFollow,
		pauseCameraFollow,
		resumeCameraFollow,
		jumpToNextHighlight,
		receiptBeatToEffectCue,
	};
}
