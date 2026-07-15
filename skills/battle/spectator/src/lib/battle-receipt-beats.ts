import type {
	BattleEffectCue,
	BattleEffectCueKind,
	BattleEvent,
	BattleNormalizedUxFixture,
	Lane,
	LaneEvent,
	SoundCue,
} from "./battle-types";
import { KILL_SHOT_TRAVEL_SECONDS, killShotVariant, resolveKillShotImpact } from "../engine/battle-pixi-kill-shot";
import { eventElapsedSeconds, fixtureUsesElapsedAxis } from "./battle-elapsed-axis";
import { battleTimelineDomain } from "./battle-timeline-domain";
import { hungerGamesNotification, type HungerGamesTicker } from "./battle-hunger-games-notifications";
import {
	isGeneticLaneEventKind,
	type GeneticPixiEffect,
} from "./battle-genetic-lifecycle";

export type ReceiptBeatKind = BattleEffectCueKind | "kill_impact" | "block_impact";
export type ReceiptBeatImportance = "hero" | "standard";
export type ReceiptBeatProofStatus = "receipt_backed" | "live" | "design_fixture";

export type ReceiptBeatCamera = {
	focusSeconds: number;
	preRollMs: number;
	postRollMs: number;
	follow: boolean;
};

export type ReceiptBeatReact = {
	liveEvent: HungerGamesTicker;
	deathCard: boolean;
	soundCue: SoundCue;
};

export type ReceiptBeatPixi = {
	emphasis:
		| "none"
		| "kill_shot_travel"
		| "kill_impact"
		| "block_impact"
		| "spawn"
		| "terminal"
		| GeneticPixiEffect;
};

/** Director manifest beat — single source for React chrome and Pixi emphasis. */
export type ReceiptBeat = {
	id: string;
	atSeconds: number;
	kind: ReceiptBeatKind;
	importance: ReceiptBeatImportance;
	proofStatus: ReceiptBeatProofStatus;
	laneId: string;
	branchIds: string[];
	eventId: string;
	receiptId: string;
	camera: ReceiptBeatCamera;
	react: ReceiptBeatReact;
	pixi: ReceiptBeatPixi;
};

function proofStatus(fixture: BattleNormalizedUxFixture): ReceiptBeatProofStatus {
	return fixture.proof_mode === "receipt_backed_fixture" ? "receipt_backed" : "design_fixture";
}

function branchIdsForLane(lane: Lane, lanes: Lane[]): string[] {
	const ids = [lane.id];
	if (lane.parentId) ids.push(lane.parentId);
	for (const childId of lane.children ?? []) ids.push(childId);
	return [...new Set(ids)];
}

function soundForKind(kind: ReceiptBeatKind, laneEvent?: LaneEvent): SoundCue {
	if (kind === "kill_impact" || kind === "killed") return "kill_cannon";
	if (kind === "blue_blast" && laneEvent && killShotVariant(laneEvent) === "kill_cannon") return "kill_cannon";
	if (kind === "blue_blast") return "blue_blast";
	if (kind === "blocked" || kind === "block_impact") return "blue_blast";
	if (kind === "spawn") return "spawn_rise";
	if (isGeneticLaneEventKind(kind)) {
		if (kind === "compile_failed" || kind === "method_rejected" || kind === "branch_abandoned") return "retry_tick";
		if (kind === "genome_selected" || kind === "method_added") return "mutate_chirp";
		if (kind === "judge_exploit_success") return "victory_hit";
		if (kind === "genome_promoted") return "scan_ping";
		return "scan_ping";
	}
	return "none";
}

function cueKindForReact(kind: ReceiptBeatKind): BattleEffectCueKind {
	if (kind === "kill_impact") return "killed";
	if (kind === "block_impact") return "blocked";
	if (kind === "spawn") return "spawn";
	if (isGeneticLaneEventKind(kind)) return kind;
	return kind as BattleEffectCueKind;
}

function cameraForKind(kind: ReceiptBeatKind): Pick<ReceiptBeatCamera, "preRollMs" | "postRollMs" | "follow"> {
	switch (kind) {
		case "kill_impact":
			return { preRollMs: 180, postRollMs: 2200, follow: true };
		case "spawn":
			return { preRollMs: 360, postRollMs: 1400, follow: true };
		case "block_impact":
			return { preRollMs: 220, postRollMs: 1800, follow: true };
		case "blue_blast":
			return { preRollMs: 90, postRollMs: 520, follow: false };
		case "killed":
			return { preRollMs: 160, postRollMs: 2000, follow: true };
		case "blocked":
			return { preRollMs: 200, postRollMs: 1200, follow: true };
		default:
			return { preRollMs: 120, postRollMs: 800, follow: false };
	}
}

function pixiEmphasisForKind(kind: ReceiptBeatKind, laneEvent?: LaneEvent): ReceiptBeatPixi["emphasis"] {
	switch (kind) {
		case "blue_blast":
			return "kill_shot_travel";
		case "kill_impact":
			return "kill_impact";
		case "block_impact":
			return "block_impact";
		case "spawn":
			return "spawn";
		case "killed":
		case "blocked":
		case "promoted":
		case "fastest_crash":
			return "terminal";
		default:
			if (isGeneticLaneEventKind(kind)) {
				return (laneEvent?.geneticEffect ?? kind) as ReceiptBeatPixi["emphasis"];
			}
			return "none";
	}
}

function pushBeat(beats: ReceiptBeat[], beat: ReceiptBeat) {
	beats.push(beat);
}

const ADAPTIVE_MEMORY_RECEIPT_LABELS = new Set([
	"MEMORY PROMOTED · PENDING",
	"MEMORY WRITTEN",
	"MEMORY RECALLED",
]);

function makeBeat(args: {
	fixture: BattleNormalizedUxFixture;
	lanes: Lane[];
	lane: Lane;
	laneEvent: LaneEvent;
	atSeconds: number;
	kind: ReceiptBeatKind;
	importance?: ReceiptBeatImportance;
	focusSeconds?: number;
	follow?: boolean;
	deathCard?: boolean;
	id?: string;
}): ReceiptBeat {
	const { fixture, lanes, lane, laneEvent, atSeconds, kind } = args;
	const reactKind = cueKindForReact(kind);
	const adaptiveLineageLabels = new Set(["CHILD RESEARCH ACTIVE", "MUTATION EVIDENCE VERIFIED"]);
	const adaptiveMemoryLabels = new Set([
		"MEMORY PROMOTED · PENDING",
		"MEMORY WRITTEN",
		"MEMORY RECALLED",
		"MEMORY USE ACKNOWLEDGED",
	]);
	const adaptiveLabel = laneEvent.label && (adaptiveLineageLabels.has(laneEvent.label) || adaptiveMemoryLabels.has(laneEvent.label))
		? laneEvent.label
		: null;
	const adaptivePrefix = adaptiveLabel && adaptiveMemoryLabels.has(adaptiveLabel)
		? "Adaptive memory — "
		: "Adaptive lineage — ";
	const ticker = adaptiveLabel
		? {
			prefix: adaptivePrefix,
			highlight: `${(lane.name || lane.id).toUpperCase()}: ${adaptiveLabel}`,
			highlightTone: "green" as const,
			notification: `${adaptivePrefix}${(lane.name || lane.id).toUpperCase()}: ${adaptiveLabel}`,
		}
		: hungerGamesNotification(reactKind, lane);
	return {
		id: args.id ?? `${lane.id}:${kind}:${atSeconds.toFixed(3)}`,
		atSeconds,
		kind,
		importance: args.importance ?? (kind === "kill_impact" || kind === "killed" || kind === "spawn" ? "hero" : "standard"),
		proofStatus: proofStatus(fixture),
		laneId: lane.id,
		branchIds: branchIdsForLane(lane, lanes),
		eventId: laneEvent.id,
		receiptId: laneEvent.receiptId ?? "",
		camera: {
			focusSeconds: args.focusSeconds ?? atSeconds,
			...cameraForKind(kind),
			follow: args.follow ?? cameraForKind(kind).follow,
		},
		react: {
			liveEvent: ticker,
			deathCard: args.deathCard ?? (kind === "kill_impact" || kind === "killed"),
			soundCue: soundForKind(kind, laneEvent),
		},
		pixi: { emphasis: pixiEmphasisForKind(kind, laneEvent) },
	};
}

export function collectReceiptBeats(fixture: BattleNormalizedUxFixture, lanes: Lane[]): ReceiptBeat[] {
	const domain = battleTimelineDomain(fixture, false);
	const allottedSeconds = domain.allottedSeconds;
	const useElapsed = fixtureUsesElapsedAxis(fixture);
	const beats: ReceiptBeat[] = [];

	for (const lane of lanes) {
		for (const laneEvent of lane.events) {
			if (!laneEvent.proven) continue;
			const atSeconds = eventElapsedSeconds(laneEvent, allottedSeconds, useElapsed);

			if (laneEvent.kind === "useful" && laneEvent.label && ADAPTIVE_MEMORY_RECEIPT_LABELS.has(laneEvent.label)) {
				pushBeat(
					beats,
					makeBeat({
						fixture,
						lanes,
						lane,
						laneEvent,
						atSeconds,
						kind: "useful",
						follow: false,
						deathCard: false,
					}),
				);
				continue;
			}

			if (laneEvent.kind === "handoff") {
				pushBeat(
					beats,
					makeBeat({
						fixture,
						lanes,
						lane,
						laneEvent,
						atSeconds,
						kind: "spawn",
						importance: "hero",
						follow: true,
						deathCard: false,
					}),
				);
				continue;
			}

			if (laneEvent.kind === "blue_blast") {
				pushBeat(
					beats,
					makeBeat({
						fixture,
						lanes,
						lane,
						laneEvent,
						atSeconds,
						kind: "blue_blast",
						focusSeconds: atSeconds,
						follow: false,
						deathCard: false,
					}),
				);
				const impactAt = atSeconds + KILL_SHOT_TRAVEL_SECONDS;
				const impactKind = resolveKillShotImpact(lane, laneEvent, allottedSeconds, useElapsed);
				const terminalEvent =
					lane.events.find((event) => event.proven && (event.kind === "killed" || event.kind === "blocked")) ?? laneEvent;
				if (impactKind === "killed") {
					pushBeat(
						beats,
						makeBeat({
							fixture,
							lanes,
							lane,
							laneEvent: terminalEvent,
							atSeconds: impactAt,
							kind: "kill_impact",
							importance: "hero",
							focusSeconds: impactAt,
							follow: true,
							deathCard: true,
							id: `${laneEvent.id}:kill-impact`,
						}),
					);
				} else if (impactKind === "blocked") {
					pushBeat(
						beats,
						makeBeat({
							fixture,
							lanes,
							lane,
							laneEvent: terminalEvent,
							atSeconds: impactAt,
							kind: "block_impact",
							focusSeconds: impactAt,
							follow: true,
							deathCard: false,
							id: `${laneEvent.id}:block-impact`,
						}),
					);
				}
				continue;
			}

			if (laneEvent.kind === "killed" || laneEvent.kind === "blocked") {
				const hasBlueBlast = lane.events.some(
					(event) =>
						event.proven &&
						event.kind === "blue_blast" &&
						eventElapsedSeconds(event, allottedSeconds, useElapsed) <= atSeconds,
				);
				if (hasBlueBlast) continue;
				pushBeat(
					beats,
					makeBeat({
						fixture,
						lanes,
						lane,
						laneEvent,
						atSeconds,
						kind: laneEvent.kind,
						follow: laneEvent.kind === "killed",
						deathCard: laneEvent.kind === "killed",
					}),
				);
				continue;
			}

			if (isGeneticLaneEventKind(laneEvent.kind)) {
				// Fail-closed: genetic lifecycle never emits death/victory cards here.
				const victory = Boolean(laneEvent.victoryAllowed);
				pushBeat(
					beats,
					makeBeat({
						fixture,
						lanes,
						lane,
						laneEvent,
						atSeconds,
						kind: victory ? "promoted" : (laneEvent.kind as ReceiptBeatKind),
						importance: "hero",
						follow: true,
						deathCard: false,
					}),
				);
			}
		}
	}

	return beats.sort((a, b) => a.atSeconds - b.atSeconds || a.id.localeCompare(b.id));
}

export function heroReceiptBeats(beats: ReceiptBeat[]): ReceiptBeat[] {
	return beats.filter((beat) => beat.importance === "hero");
}

export function nextReceiptBeat(beats: ReceiptBeat[], currentSeconds: number): ReceiptBeat | null {
	return beats.find((beat) => beat.atSeconds > currentSeconds + 0.05) ?? null;
}


const SURVIVAL_TICKER_KINDS = new Set<ReceiptBeatKind>(["blue_blast", "block_impact", "blocked"]);
const TERMINAL_KILL_KINDS = new Set<ReceiptBeatKind>(["kill_impact", "killed"]);

/** Suppress stale survival highlights once a lane has a confirmed kill at or before playhead. */
export function receiptBeatsForTicker(beats: ReceiptBeat[], playheadSeconds: number, limit = 3): ReceiptBeat[] {
	const eligible = beats.filter((beat) => beat.atSeconds <= playheadSeconds + 0.001);
	const suppressed = new Set<string>();
	for (const laneId of new Set(eligible.map((beat) => beat.laneId))) {
		const laneBeats = eligible.filter((beat) => beat.laneId === laneId);
		const killBeat = laneBeats.filter((beat) => TERMINAL_KILL_KINDS.has(beat.kind)).at(-1);
		if (!killBeat) continue;
		for (const beat of laneBeats) {
			if (beat.id === killBeat.id) continue;
			if (!SURVIVAL_TICKER_KINDS.has(beat.kind)) continue;
			if (beat.atSeconds + 0.001 < killBeat.atSeconds) suppressed.add(beat.id);
		}
	}
	return eligible.filter((beat) => !suppressed.has(beat.id)).slice(-limit);
}

export function receiptBeatsVisibleAtPlayhead(beats: ReceiptBeat[], playheadSeconds: number, limit = 3): ReceiptBeat[] {
	return receiptBeatsForTicker(beats, playheadSeconds, limit);
}

export function highlightReelDwellMs(beat: ReceiptBeat): number {
	return beat.camera.preRollMs + beat.camera.postRollMs;
}

export function highlightReelPreRollSeconds(beat: ReceiptBeat): number {
	return beat.camera.preRollMs / 1000;
}

export function activeReceiptBeatAtPlayhead(
	beats: ReceiptBeat[],
	playheadSeconds: number,
	activeBeat: ReceiptBeat | null = null,
): ReceiptBeat | null {
	if (activeBeat) return activeBeat;
	return receiptBeatsVisibleAtPlayhead(beats, playheadSeconds, 1).at(-1) ?? null;
}

function crossedForward(prevSeconds: number, nextSeconds: number, atSeconds: number): boolean {
	return prevSeconds + 0.0001 < atSeconds && nextSeconds + 0.0001 >= atSeconds;
}

export function collectReceiptBeatCrossings(args: {
	prevSeconds: number;
	nextSeconds: number;
	beats: ReceiptBeat[];
}): ReceiptBeat[] {
	const { prevSeconds, nextSeconds, beats } = args;
	if (nextSeconds <= prevSeconds) return [];
	return beats.filter((beat) => crossedForward(prevSeconds, nextSeconds, beat.atSeconds));
}

export function receiptBeatToEffectCue(beat: ReceiptBeat): BattleEffectCue {
	return {
		eventId: beat.eventId,
		laneId: beat.laneId,
		cue: cueKindForReact(beat.kind),
		atSeconds: beat.atSeconds,
		receiptId: beat.receiptId,
		proofMode: beat.proofStatus === "receipt_backed" ? "receipt_backed" : "design_fixture",
		soundCue: beat.react.soundCue,
		notification: beat.react.liveEvent.notification,
	};
}

export function receiptBeatToBattleEvent(beat: ReceiptBeat, fixture: BattleNormalizedUxFixture): BattleEvent {
	const team = beat.kind === "blue_blast" || beat.kind === "block_impact" || beat.kind === "blocked" ? "blue" : "red";
	const reactCue = cueKindForReact(beat.kind);
	const eventType = isGeneticLaneEventKind(reactCue) ? reactCue : (`replay.${reactCue}` as BattleEvent["event_type"]);
	return {
		id: beat.id,
		ts: new Date(0).toISOString(),
		battle_id: fixture.battle_id,
		team,
		actor_id: beat.laneId,
		actor_kind: team === "blue" ? "patch_agent" : "exploit_agent",
		event_type: eventType,
		summary: beat.react.liveEvent.notification,
		proof_mode: fixture.proof_mode,
		ui: {
			notification: beat.react.liveEvent.notification,
			notification_prefix: beat.react.liveEvent.prefix,
			notification_highlight: beat.react.liveEvent.highlight,
			notification_highlight_tone: beat.react.liveEvent.highlightTone,
			sound_cue: beat.react.soundCue,
			importance: beat.importance,
		},
	} as unknown as BattleEvent;
}
