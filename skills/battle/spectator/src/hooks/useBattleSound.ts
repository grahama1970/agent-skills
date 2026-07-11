import { useCallback, useRef, useState } from "react";
import type { SoundCue } from "../lib/battle-types";

type Osc = OscillatorNode;

export function useBattleSound() {
	const ctxRef = useRef<AudioContext | null>(null);
	const [enabled, setEnabled] = useState(false);

	const ensure = useCallback(() => {
		if (!ctxRef.current) {
			ctxRef.current = new AudioContext();
		}
		if (ctxRef.current.state === "suspended") void ctxRef.current.resume();
		setEnabled(true);
		return ctxRef.current;
	}, []);

	const beep = useCallback(
		(freq: number, duration = 0.12, gain = 0.08, type: OscillatorType = "sine") => {
			const ctx = ensure();
			const osc: Osc = ctx.createOscillator();
			const g = ctx.createGain();
			osc.type = type;
			osc.frequency.setValueAtTime(freq, ctx.currentTime);
			g.gain.setValueAtTime(gain, ctx.currentTime);
			g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + duration);
			osc.connect(g);
			g.connect(ctx.destination);
			osc.start();
			osc.stop(ctx.currentTime + duration);
		},
		[ensure],
	);

	const play = useCallback(
		(cue: SoundCue | undefined) => {
			if (!cue || cue === "none") return;
			switch (cue) {
				case "scan_ping":
					beep(880, 0.08, 0.06, "triangle");
					break;
				case "mutate_chirp":
					beep(520, 0.08, 0.05, "sawtooth");
					setTimeout(() => beep(720, 0.08, 0.04, "sawtooth"), 70);
					break;
				case "retry_tick":
					beep(300, 0.06, 0.04, "square");
					break;
				case "blue_patch_deploy":
					beep(180, 0.12, 0.06, "sawtooth");
					setTimeout(() => beep(360, 0.16, 0.05, "triangle"), 90);
					break;
				case "blue_blast":
					beep(120, 0.25, 0.1, "sawtooth");
					setTimeout(() => beep(260, 0.14, 0.08, "square"), 55);
					break;
				case "kill_cannon":
					beep(90, 0.35, 0.12, "sawtooth");
					setTimeout(() => beep(55, 0.4, 0.09, "square"), 120);
					break;
				case "spawn_rise":
					beep(440, 0.12, 0.06, "triangle");
					setTimeout(() => beep(660, 0.12, 0.06, "triangle"), 100);
					break;
				case "victory_hit":
					beep(440, 0.08, 0.07, "triangle");
					setTimeout(() => beep(660, 0.1, 0.06, "triangle"), 80);
					setTimeout(() => beep(990, 0.16, 0.05, "triangle"), 170);
					break;
			}
		},
		[beep],
	);

	const getContext = useCallback(() => ensure(), [ensure]);
	return { enabled, arm: ensure, play, getContext };
}
