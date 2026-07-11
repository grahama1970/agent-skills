/**
 * Minimal Type-0/1 MIDI parser + WebAudio playback tuned for Genesis-like timbres.
 * Plays the bundled original round-intro MIDI (not commercial VGM dumps).
 */

export type GenesisMidiNoteEvent = {
	tick: number;
	type: "on" | "off";
	channel: number;
	note: number;
	velocity: number;
};

export type GenesisMidiSong = {
	ticksPerQuarter: number;
	tempoBpm: number;
	events: GenesisMidiNoteEvent[];
	durationTicks: number;
	sourceUrl: string;
};

const DEFAULT_MIDI_URL = "/battle-audio/battle-004-round-intro.mid";

function readU32(view: DataView, offset: number): number {
	return view.getUint32(offset);
}

function readU16(view: DataView, offset: number): number {
	return view.getUint16(offset);
}

function readVlq(bytes: Uint8Array, offset: number): { value: number; next: number } {
	let value = 0;
	let i = offset;
	while (i < bytes.length) {
		const b = bytes[i++]!;
		value = (value << 7) | (b & 0x7f);
		if ((b & 0x80) === 0) break;
	}
	return { value, next: i };
}

export function parseMidiBytes(buffer: ArrayBuffer, sourceUrl: string): GenesisMidiSong {
	const bytes = new Uint8Array(buffer);
	const view = new DataView(buffer);
	if (String.fromCharCode(...bytes.slice(0, 4)) !== "MThd") {
		throw new Error("Not a MIDI file");
	}
	const headerLen = readU32(view, 4);
	const ticksPerQuarter = readU16(view, 12);
	let offset = 8 + headerLen;
	const events: GenesisMidiNoteEvent[] = [];
	let tempoBpm = 120;
	let durationTicks = 0;

	while (offset + 8 <= bytes.length) {
		const chunkType = String.fromCharCode(...bytes.slice(offset, offset + 4));
		const chunkLen = readU32(view, offset + 4);
		const start = offset + 8;
		const end = start + chunkLen;
		if (chunkType !== "MTrk") {
			offset = end;
			continue;
		}
		let i = start;
		let tick = 0;
		let running = 0;
		while (i < end) {
			const vlq = readVlq(bytes, i);
			tick += vlq.value;
			i = vlq.next;
			let status = bytes[i++]!;
			if (status < 0x80) {
				i -= 1;
				status = running;
			} else {
				running = status;
			}
			const high = status & 0xf0;
			const channel = status & 0x0f;
			if (status === 0xff) {
				const meta = bytes[i++]!;
				const len = bytes[i++]!;
				if (meta === 0x51 && len === 3) {
					const us = (bytes[i]! << 16) | (bytes[i + 1]! << 8) | bytes[i + 2]!;
					tempoBpm = Math.round(60_000_000 / us);
				}
				i += len;
			} else if (high === 0x90 || high === 0x80) {
				const note = bytes[i++]!;
				const velocity = bytes[i++]!;
				const type = high === 0x90 && velocity > 0 ? "on" : "off";
				events.push({ tick, type, channel, note, velocity: type === "on" ? velocity : 0 });
				durationTicks = Math.max(durationTicks, tick);
			} else if (high === 0xc0 || high === 0xd0) {
				i += 1;
			} else if (high === 0xb0 || high === 0xa0 || high === 0xe0) {
				i += 2;
			} else if (status === 0xf0 || status === 0xf7) {
				const lenInfo = readVlq(bytes, i);
				i = lenInfo.next + lenInfo.value;
			} else {
				break;
			}
		}
		offset = end;
	}

	events.sort((a, b) => a.tick - b.tick || (a.type === "off" ? -1 : 1));
	return { ticksPerQuarter, tempoBpm, events, durationTicks, sourceUrl };
}

export async function loadGenesisRoundIntroMidi(
	url = DEFAULT_MIDI_URL,
): Promise<GenesisMidiSong> {
	const response = await fetch(url);
	if (!response.ok) throw new Error(`Failed to load MIDI ${url} (${response.status})`);
	return parseMidiBytes(await response.arrayBuffer(), url);
}

function midiNoteToHz(note: number): number {
	return 440 * 2 ** ((note - 69) / 12);
}

function waveForChannel(channel: number): OscillatorType {
	if (channel === 9) return "square";
	if (channel === 1) return "triangle";
	return "square";
}

export type GenesisMidiPlayer = {
	playing: boolean;
	sourceUrl: string | null;
	start: (song?: GenesisMidiSong) => Promise<void>;
	stop: () => void;
};

/** Looping Genesis-timbred MIDI player using Web Audio oscillators. */
export function createGenesisMidiPlayer(getContext: () => AudioContext): GenesisMidiPlayer {
	let playing = false;
	let sourceUrl: string | null = null;
	let timer: number | null = null;
	const active = new Map<string, { osc: OscillatorNode; gain: GainNode }>();

	const stopVoices = () => {
		for (const voice of active.values()) {
			try {
				voice.gain.gain.cancelScheduledValues(0);
				voice.osc.stop();
			} catch {
				/* already stopped */
			}
		}
		active.clear();
	};

	const stop = () => {
		playing = false;
		if (timer != null) {
			window.clearTimeout(timer);
			timer = null;
		}
		stopVoices();
	};

	const schedule = (song: GenesisMidiSong, ctx: AudioContext) => {
		stopVoices();
		const secondsPerTick = 60 / song.tempoBpm / song.ticksPerQuarter;
		const startAt = ctx.currentTime + 0.05;
		for (const event of song.events) {
			const when = startAt + event.tick * secondsPerTick;
			const key = `${event.channel}:${event.note}`;
			if (event.type === "on") {
				const osc = ctx.createOscillator();
				const gain = ctx.createGain();
				osc.type = waveForChannel(event.channel);
				osc.frequency.setValueAtTime(midiNoteToHz(event.note), when);
				const amp = Math.max(0.02, (event.velocity / 127) * (event.channel === 9 ? 0.045 : 0.07));
				gain.gain.setValueAtTime(0.0001, when);
				gain.gain.exponentialRampToValueAtTime(amp, when + 0.01);
				osc.connect(gain);
				gain.connect(ctx.destination);
				osc.start(when);
				active.set(key, { osc, gain });
			} else {
				const voice = active.get(key);
				if (!voice) continue;
				voice.gain.gain.cancelScheduledValues(when);
				voice.gain.gain.setValueAtTime(Math.max(voice.gain.gain.value, 0.0001), when);
				voice.gain.gain.exponentialRampToValueAtTime(0.0001, when + 0.05);
				try {
					voice.osc.stop(when + 0.06);
				} catch {
					/* ignore */
				}
				active.delete(key);
			}
		}
		const durationMs = Math.max(500, song.durationTicks * secondsPerTick * 1000 + 200);
		timer = window.setTimeout(() => {
			if (!playing) return;
			schedule(song, ctx);
		}, durationMs);
	};

	return {
		get playing() {
			return playing;
		},
		get sourceUrl() {
			return sourceUrl;
		},
		async start(song) {
			const ctx = getContext();
			if (ctx.state === "suspended") await ctx.resume();
			const resolved = song ?? (await loadGenesisRoundIntroMidi());
			sourceUrl = resolved.sourceUrl;
			playing = true;
			schedule(resolved, ctx);
		},
		stop,
	};
}

export { DEFAULT_MIDI_URL as BATTLE_GENESIS_ROUND_INTRO_MIDI_URL };
