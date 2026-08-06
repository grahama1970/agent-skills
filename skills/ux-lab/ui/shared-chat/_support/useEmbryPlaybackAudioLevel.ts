import { useEffect, useRef, useState } from "react";

type AudioAnalyserEntry = {
	ctx: AudioContext;
	analyser: AnalyserNode;
};

export type EmbryPlaybackAudioBands = {
	level: number;
	bass: number;
	mid: number;
	treble: number;
};

export type EmbryVoiceEnvelope = {
	version?: 1;
	frameMs?: number;
	durationMs?: number;
	stats?: {
		rmsP10?: number;
		rmsP95?: number;
		peakP95?: number;
	};
	frames: Array<EmbryPlaybackAudioBands & { t: number }>;
};

const analyserCache = new WeakMap<HTMLMediaElement, AudioAnalyserEntry>();
const decodedAudioCache = new Map<string, Promise<AudioBuffer>>();

function analyserFor(audio: HTMLMediaElement): AudioAnalyserEntry {
	let entry = analyserCache.get(audio);
	if (!entry) {
		const ctx = new AudioContext();
		const analyser = ctx.createAnalyser();
		analyser.fftSize = 256;
		analyser.smoothingTimeConstant = 0.75;
		const source = ctx.createMediaElementSource(audio);
		source.connect(analyser);
		analyser.connect(ctx.destination);
		entry = { ctx, analyser };
		analyserCache.set(audio, entry);
	}
	if (entry.ctx.state === "suspended") void entry.ctx.resume();
	return entry;
}

function averageRange(data: Uint8Array, start: number, end: number): number {
	let sum = 0;
	const safeStart = Math.max(0, Math.min(data.length, start));
	const safeEnd = Math.max(safeStart + 1, Math.min(data.length, end));
	for (let i = safeStart; i < safeEnd; i += 1) sum += data[i];
	return sum / (safeEnd - safeStart) / 255;
}

function bandsFromAnalyser(analyser: AnalyserNode): EmbryPlaybackAudioBands {
	const data = new Uint8Array(analyser.frequencyBinCount);
	analyser.getByteFrequencyData(data);
	const level = Math.min(1, averageRange(data, 0, data.length) * 1.8);
	return {
		level,
		bass: Math.min(1, averageRange(data, 0, 8) * 2.1),
		mid: Math.min(1, averageRange(data, 8, 36) * 1.9),
		treble: Math.min(1, averageRange(data, 36, data.length) * 2.4),
	};
}

const silentBands: EmbryPlaybackAudioBands = { level: 0, bass: 0, mid: 0, treble: 0 };

function audioContextForDecode(): AudioContext {
	const AudioContextCtor =
		window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
	if (!AudioContextCtor) throw new Error("AudioContext is unavailable");
	return new AudioContextCtor();
}

function decodedBufferFor(url: string): Promise<AudioBuffer> {
	const cached = decodedAudioCache.get(url);
	if (cached) return cached;
	const promise = (async () => {
		const response = await fetch(url);
		if (!response.ok) throw new Error(`failed to fetch audio ${response.status}`);
		const arrayBuffer = await response.arrayBuffer();
		const ctx = audioContextForDecode();
		try {
			return await ctx.decodeAudioData(arrayBuffer.slice(0));
		} finally {
			void ctx.close().catch(() => undefined);
		}
	})();
	decodedAudioCache.set(url, promise);
	return promise;
}

function bandsFromDecodedBuffer(buffer: AudioBuffer, elapsedSeconds: number): EmbryPlaybackAudioBands {
	if (!Number.isFinite(elapsedSeconds) || elapsedSeconds < 0 || elapsedSeconds > buffer.duration) return silentBands;
	const channel = buffer.getChannelData(0);
	const center = Math.max(0, Math.min(channel.length - 1, Math.floor(elapsedSeconds * buffer.sampleRate)));
	const windowSize = Math.max(256, Math.floor(buffer.sampleRate * 0.035));
	const start = Math.max(0, center - Math.floor(windowSize / 2));
	const end = Math.min(channel.length, start + windowSize);
	if (end <= start) return silentBands;

	let sum = 0;
	let bassSum = 0;
	let midSum = 0;
	let trebleSum = 0;
	let prev = channel[start] ?? 0;
	for (let index = start; index < end; index += 1) {
		const sample = channel[index] ?? 0;
		const abs = Math.abs(sample);
		sum += abs;
		const delta = Math.abs(sample - prev);
		prev = sample;
		if (index % 12 === 0) bassSum += abs;
		else if (index % 4 === 0) midSum += abs + delta * 0.5;
		else trebleSum += delta;
	}
	const count = end - start;
	const level = Math.min(1, (sum / count) * 8.5);
	return {
		level,
		bass: Math.min(1, (bassSum / Math.max(1, Math.floor(count / 12))) * 9),
		mid: Math.min(1, (midSum / Math.max(1, Math.floor(count / 4))) * 7),
		treble: Math.min(1, (trebleSum / count) * 42),
	};
}

export function useEmbryPlaybackAudioBands(
	enabled = true,
	audioElement?: HTMLMediaElement | null,
): EmbryPlaybackAudioBands {
	const [bands, setBands] = useState<EmbryPlaybackAudioBands>(silentBands);
	const rafRef = useRef(0);

	useEffect(() => {
		if (!enabled || typeof window === "undefined" || !audioElement) {
			return;
		}

		const tick = () => {
			const playing = !audioElement.paused && !audioElement.ended && audioElement.currentTime > 0;
			setBands(playing ? bandsFromAnalyser(analyserFor(audioElement).analyser) : silentBands);
			rafRef.current = requestAnimationFrame(tick);
		};

		rafRef.current = requestAnimationFrame(tick);
		return () => cancelAnimationFrame(rafRef.current);
	}, [audioElement, enabled]);

	return enabled && audioElement ? bands : silentBands;
}

export function useEmbryPlaybackAudioLevel(enabled = true, audioElement?: HTMLMediaElement | null): number {
	return useEmbryPlaybackAudioBands(enabled, audioElement).level;
}

export function useEmbryDecodedAudioBands(
	enabled = true,
	audioUrl?: string,
	startedAtMs?: number,
): EmbryPlaybackAudioBands {
	const [bufferEntry, setBufferEntry] = useState<{ url: string; buffer: AudioBuffer } | null>(null);
	const [bands, setBands] = useState<EmbryPlaybackAudioBands>(silentBands);
	const rafRef = useRef(0);

	useEffect(() => {
		let cancelled = false;
		if (!enabled || !audioUrl || typeof window === "undefined") return;
		decodedBufferFor(audioUrl)
			.then((decoded) => {
				if (!cancelled) setBufferEntry({ url: audioUrl, buffer: decoded });
			})
			.catch(() => {
				if (!cancelled) setBufferEntry((current) => (current?.url === audioUrl ? null : current));
			});
		return () => {
			cancelled = true;
		};
	}, [audioUrl, enabled]);

	useEffect(() => {
		const buffer = bufferEntry && bufferEntry.url === audioUrl ? bufferEntry.buffer : null;
		if (!enabled || !buffer || startedAtMs == null) {
			return;
		}
		const tick = () => {
			const elapsedSeconds = (performance.now() - startedAtMs) / 1000;
			setBands(bandsFromDecodedBuffer(buffer, elapsedSeconds));
			if (elapsedSeconds <= buffer.duration + 0.2) rafRef.current = requestAnimationFrame(tick);
		};
		rafRef.current = requestAnimationFrame(tick);
		return () => cancelAnimationFrame(rafRef.current);
	}, [audioUrl, bufferEntry, enabled, startedAtMs]);

	return enabled && bufferEntry?.url === audioUrl ? bands : silentBands;
}

export function useEmbryEnvelopeAudioBands(
	enabled = true,
	envelope?: EmbryVoiceEnvelope,
	startedAtMs?: number,
): EmbryPlaybackAudioBands {
	const [bands, setBands] = useState<EmbryPlaybackAudioBands>(silentBands);
	const rafRef = useRef(0);

	useEffect(() => {
		if (!enabled || startedAtMs == null || !envelope?.frames.length) return;
		const tick = () => {
			const elapsedMs = performance.now() - startedAtMs;
			const elapsedSeconds = elapsedMs / 1000;
			const frameMs = envelope.frameMs && envelope.frameMs > 0 ? envelope.frameMs : 40;
			const index = Math.max(0, Math.min(envelope.frames.length - 1, Math.floor((elapsedSeconds * 1000) / frameMs)));
			const frame = envelope.frames[index] ?? silentBands;
			const durationMs = envelope.durationMs ?? envelope.frames.length * frameMs;
			const active = elapsedMs >= 0 && elapsedMs <= durationMs + 250;
			setBands({
				level: active ? frame.level : 0,
				bass: active ? frame.bass : 0,
				mid: active ? frame.mid : 0,
				treble: active ? frame.treble : 0,
			});
			if (active) rafRef.current = requestAnimationFrame(tick);
		};
		rafRef.current = requestAnimationFrame(tick);
		return () => cancelAnimationFrame(rafRef.current);
	}, [enabled, envelope, startedAtMs]);

	return enabled && envelope?.frames.length ? bands : silentBands;
}
