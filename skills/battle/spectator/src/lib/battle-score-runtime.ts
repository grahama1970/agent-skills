/**
 * WebAudio OGG score bus for Battle cues + sprite motifs.
 * Duck loop hook during stingers; fail-closed callers supply receipt-backed triggers only.
 */
import {
	BATTLE_SCORE_CUES,
	BATTLE_SCORE_PROVISIONAL_GM_RENDER,
	BATTLE_SPRITE_MOTIFS,
	type BattleScoreCueId,
	motifSpecForSprite,
} from "./battle-music-catalog";

export type BattleScoreRuntime = {
	provisionalGmRender: true;
	arm: () => AudioContext;
	playCue: (cueId: BattleScoreCueId) => Promise<void>;
	playMotif: (spriteId: string) => Promise<boolean>;
	startLoop: () => Promise<void>;
	stopLoop: () => void;
	stopAll: () => void;
	isLoopPlaying: () => boolean;
	activeCueId: () => BattleScoreCueId | "motif" | null;
};

type Voice = {
	source: AudioBufferSourceNode;
	gain: GainNode;
	cueId: BattleScoreCueId | "motif";
};

export function createBattleScoreRuntime(getContext: () => AudioContext): BattleScoreRuntime {
	const buffers = new Map<string, AudioBuffer>();
	let loopVoice: Voice | null = null;
	let overlayVoice: Voice | null = null;
	let active: BattleScoreCueId | "motif" | null = null;
	let loopGainNode: GainNode | null = null;

	const decode = async (url: string): Promise<AudioBuffer> => {
		const hit = buffers.get(url);
		if (hit) return hit;
		const res = await fetch(url);
		if (!res.ok) throw new Error(`score fetch failed ${res.status}: ${url}`);
		const ctx = getContext();
		const raw = await res.arrayBuffer();
		const buf = await ctx.decodeAudioData(raw.slice(0));
		buffers.set(url, buf);
		return buf;
	};

	const stopVoice = (voice: Voice | null) => {
		if (!voice) return;
		try {
			voice.source.stop();
		} catch {
			/* already stopped */
		}
		try {
			voice.source.disconnect();
			voice.gain.disconnect();
		} catch {
			/* ignore */
		}
	};

	const duckLoop = (duck: boolean) => {
		if (!loopGainNode) return;
		const ctx = getContext();
		const target = duck ? 0.28 : 0.55;
		loopGainNode.gain.cancelScheduledValues(ctx.currentTime);
		loopGainNode.gain.setTargetAtTime(target, ctx.currentTime, 0.05);
	};

	const playBuffer = async (
		url: string,
		cueId: BattleScoreCueId | "motif",
		opts: { loop?: boolean; gain?: number; asLoop?: boolean } = {},
	) => {
		const ctx = getContext();
		if (ctx.state === "suspended") await ctx.resume();
		const buffer = await decode(url);
		const source = ctx.createBufferSource();
		const gain = ctx.createGain();
		source.buffer = buffer;
		source.loop = Boolean(opts.loop);
		gain.gain.value = opts.gain ?? 0.7;
		source.connect(gain);
		gain.connect(ctx.destination);
		const voice: Voice = { source, gain, cueId };
		if (opts.asLoop) {
			stopVoice(loopVoice);
			loopVoice = voice;
			loopGainNode = gain;
		} else {
			stopVoice(overlayVoice);
			overlayVoice = voice;
			duckLoop(true);
			source.onended = () => {
				if (overlayVoice === voice) {
					overlayVoice = null;
					if (active === cueId) active = loopVoice ? "live_arena_loop" : null;
					duckLoop(false);
				}
			};
		}
		active = cueId;
		source.start();
	};

	return {
		provisionalGmRender: BATTLE_SCORE_PROVISIONAL_GM_RENDER,
		arm: () => getContext(),
		async playCue(cueId) {
			const spec = BATTLE_SCORE_CUES[cueId];
			if (!spec) return;
			if (cueId === "live_arena_loop") {
				await playBuffer(spec.ogg, cueId, { loop: true, gain: 0.55, asLoop: true });
				return;
			}
			if (cueId === "next_battle_arena") {
				stopVoice(loopVoice);
				loopVoice = null;
				loopGainNode = null;
			}
			await playBuffer(spec.ogg, cueId, { loop: false, gain: cueId.includes("stinger") ? 0.85 : 0.7 });
		},
		async playMotif(spriteId) {
			const spec = motifSpecForSprite(spriteId);
			if (!spec) return false;
			await playBuffer(spec.ogg, "motif", { loop: false, gain: 0.62 });
			return true;
		},
		async startLoop() {
			await this.playCue("live_arena_loop");
		},
		stopLoop() {
			stopVoice(loopVoice);
			loopVoice = null;
			loopGainNode = null;
			if (active === "live_arena_loop") active = overlayVoice?.cueId ?? null;
		},
		stopAll() {
			stopVoice(overlayVoice);
			stopVoice(loopVoice);
			overlayVoice = null;
			loopVoice = null;
			loopGainNode = null;
			active = null;
		},
		isLoopPlaying: () => Boolean(loopVoice),
		activeCueId: () => active,
	};
}

export function knownMotifSpriteIds(): string[] {
	return Object.keys(BATTLE_SPRITE_MOTIFS);
}
