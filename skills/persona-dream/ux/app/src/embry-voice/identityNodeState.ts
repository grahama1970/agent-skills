import type { EmbryState, EmbryVoiceStatus } from "./EmbryVoiceOrb";
import { resolveEmbryVisualState } from "./embryOrbState";

export type IdentitySignal = "ready" | "busy" | "clarify" | "speaking" | "off";

export interface IdentityNodeViewModel {
	visualState: EmbryState;
	signal: IdentitySignal;
	statusLabel: string;
	modeLabel: string;
	accentColor: string;
	pulse: boolean;
}

/** Logo Lab canonical hues — synced with @embry/logo STATE_COLORS particles */
const EMBRY_STATE_ACCENT: Record<EmbryState, string> = {
	idle: "#3a91ff",
	listening: "#00dcaa",
	thinking: "#50a0ff",
	synthesizing: "#b464ff",
	speaking: "#50ffb4",
};

const SIGNAL_ACCENT: Record<IdentitySignal, string> = {
	ready: "#3a91ff",
	busy: "#fbbf24",
	clarify: "#00dcaa",
	speaking: "#50ffb4",
	off: "#52525b",
};

function statusLabelFor(visualState: EmbryState, signal: IdentitySignal): string {
	if (signal === "off") return "idle…";
	if (signal === "clarify") return "listening…";
	switch (visualState) {
		case "idle":
			return "idle…";
		case "listening":
			return "listening…";
		case "thinking":
			return "thinking…";
		case "synthesizing":
			return "answering…";
		case "speaking":
			return "answering…";
		default:
			return "idle…";
	}
}

function signalFor(visualState: EmbryState, voiceStatus: EmbryVoiceStatus | undefined, tone?: string): IdentitySignal {
	if (voiceStatus === "off") return "off";
	if (visualState === "speaking") return "speaking";
	if (tone === "identity_clarification" || tone?.includes("clarif")) return "clarify";
	if (visualState === "thinking" || visualState === "synthesizing" || visualState === "listening") return "busy";
	return "ready";
}

function accentFor(signal: IdentitySignal, visualState: EmbryState): string {
	if (signal === "clarify") return SIGNAL_ACCENT.clarify;
	if (signal === "busy") return EMBRY_STATE_ACCENT[visualState];
	return SIGNAL_ACCENT[signal];
}

export function buildIdentityNodeViewModel({
	voiceStatus,
	isStreaming,
	tone,
}: {
	voiceStatus?: EmbryVoiceStatus;
	isStreaming?: boolean;
	tone?: string;
	speaker?: string;
}): IdentityNodeViewModel {
	const visualState = voiceStatus === "off" ? "idle" : resolveEmbryVisualState({ voiceStatus, isStreaming, tone });

	const signal = signalFor(visualState, voiceStatus, tone);
	const statusLabel = statusLabelFor(visualState, signal);

	return {
		visualState,
		signal,
		statusLabel,
		modeLabel: tone ? tone.replaceAll("_", " ").toUpperCase() : "",
		accentColor: accentFor(signal, visualState),
		pulse: signal === "busy" || signal === "clarify" || signal === "speaking",
	};
}
