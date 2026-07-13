import type { Lane, LaneActivitySegment, LaneEvent, LaneTerminal } from "../lib/battle-types";
import { eventElapsedSeconds, laneElapsedRange, segmentContainsPlayhead } from "../lib/battle-elapsed-axis";
import type { BattleRunnerAnimation } from "./battle-runner-sprites";

function trackPercent(currentSeconds: number, allottedSeconds: number): number {
	return (Math.max(0, currentSeconds) / Math.max(1, allottedSeconds)) * 100;
}

function segmentAtPlayhead(
	lane: Lane,
	trackPct: number,
	currentSeconds: number,
	allottedSeconds: number,
	useElapsed: boolean,
): LaneActivitySegment | null {
	const segments = lane.activitySegments ?? [];
	for (const segment of segments) {
		if (useElapsed) {
			if (segmentContainsPlayhead(segment, currentSeconds, allottedSeconds, true)) return segment;
			continue;
		}
		if (trackPct >= segment.start_x && trackPct <= segment.end_x) return segment;
	}
	return null;
}

const TERMINAL_EVENT_KINDS: Record<LaneTerminal, LaneEvent["kind"][]> = {
	none: [],
	killed: ["killed"],
	blocked: ["blocked", "blue_blast"],
	blocked_handoff: ["handoff", "blocked", "blue_blast"],
	promoted: ["promoted"],
	fastest_crash: ["fastest_crash"],
	survivor: [],
};

function provenTerminalEvent(
	lane: Lane,
	trackPct: number,
	currentSeconds: number,
	allottedSeconds: number,
	useElapsed: boolean,
): LaneEvent | null {
	if (lane.terminal === "none") return null;
	const kinds = TERMINAL_EVENT_KINDS[lane.terminal] ?? [];
	for (const event of lane.events) {
		if (!event.proven) continue;
		if (useElapsed) {
			if (eventElapsedSeconds(event, allottedSeconds, true) > currentSeconds) continue;
		} else if (event.x > trackPct) {
			continue;
		}
		if (kinds.includes(event.kind)) return event;
	}
	return null;
}

function phaseToAnimation(phase: string): BattleRunnerAnimation {
	switch (phase) {
		case "materialize":
			return "spawn";
		case "research":
			return "research";
		case "payload":
			return "payload";
		case "useful_signal":
			return "payload";
		case "handoff":
			return "handoff";
		case "patch_gate":
			return "blocked";
		case "judge_replay":
			return "blocked";
		case "mutation_evidence":
			return "mutate";
		default:
			return "idle";
	}
}

function terminalToAnimation(terminal: LaneTerminal): BattleRunnerAnimation | null {
	switch (terminal) {
		case "killed":
			return "killed";
		case "blocked":
		case "blocked_handoff":
			return "blocked";
		case "promoted":
			return "promoted";
		case "fastest_crash":
			return "fastest_crash";
		default:
			return null;
	}
}

function runnerStateToAnimation(state: string): BattleRunnerAnimation {
	switch (state) {
		case "research":
			return "research";
		case "stderr":
		case "self_heal":
			return "hit";
		case "mutate":
			return "mutate";
		case "retry":
			return "walk";
		case "detected":
		case "blocked":
		case "blocked_handoff":
			return "blocked";
		case "killed":
			return "killed";
		case "promoted":
			return "promoted";
		case "fastest_crash":
			return "fastest_crash";
		default:
			return "run";
	}
}

function laneIsMoving(lane: Lane, currentSeconds: number, allottedSeconds: number, useElapsed = false): boolean {
	const { start, end } = laneElapsedRange(lane, allottedSeconds, useElapsed);
	return currentSeconds > start && currentSeconds < end;
}

export function runnerAnimationForLane(
	lane: Lane,
	currentSeconds: number,
	allottedSeconds: number,
	useElapsed = false,
): BattleRunnerAnimation {
	const trackPct = trackPercent(currentSeconds, allottedSeconds);

	const terminalEvent = provenTerminalEvent(lane, trackPct, currentSeconds, allottedSeconds, useElapsed);
	if (terminalEvent) {
		const terminalAnimation = terminalToAnimation(lane.terminal);
		if (terminalAnimation) return terminalAnimation;
	}

	const segment = segmentAtPlayhead(lane, trackPct, currentSeconds, allottedSeconds, useElapsed);
	if (segment) return phaseToAnimation(segment.phase);

	if (laneIsMoving(lane, currentSeconds, allottedSeconds, useElapsed)) {
		return lane.parentId ? "walk" : "run";
	}

	return runnerStateToAnimation(String(lane.runnerState));
}

export function animationSpeedFor(animation: BattleRunnerAnimation): number {
	switch (animation) {
		case "idle":
			return 0.08;
		case "walk":
			return 0.12;
		case "run":
		case "fastest_crash":
			return 0.18;
		case "hit":
			return 0.2;
		case "killed":
			return 0.14;
		default:
			return 0.15;
	}
}

export function activitySegmentAtPlayhead(
	lane: Lane,
	currentSeconds: number,
	allottedSeconds: number,
	useElapsed = false,
): LaneActivitySegment | null {
	return segmentAtPlayhead(lane, trackPercent(currentSeconds, allottedSeconds), currentSeconds, allottedSeconds, useElapsed);
}

export function isProvisionalSegment(segment: LaneActivitySegment): boolean {
	return (
		segment.proof_mode === "pending" ||
		segment.proof_mode === "missing" ||
		segment.proof_mode === "fixture" ||
		segment.proof_mode === "mocked"
	);
}

const RECEIPT_SAFE_TERMINAL_ANIMATIONS = new Set<BattleRunnerAnimation>([
	"blocked",
	"killed",
	"promoted",
	"fastest_crash",
	"victory",
]);

export function runnerAnimationWithReceiptGate(
	lane: Lane,
	currentSeconds: number,
	allottedSeconds: number,
	receiptSafe: boolean,
	useElapsed = false,
): BattleRunnerAnimation {
	const animation = runnerAnimationForLane(lane, currentSeconds, allottedSeconds, useElapsed);
	if (receiptSafe || !RECEIPT_SAFE_TERMINAL_ANIMATIONS.has(animation)) return animation;
	return laneIsMoving(lane, currentSeconds, allottedSeconds, useElapsed) ? "run" : "idle";
}
