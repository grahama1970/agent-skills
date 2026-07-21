import type { Lane, LaneEvent, LaneEventKind, RunnerState } from "../lib/battle-types";
import { geneticMarkerAtlasFrame, isGeneticLaneEventKind } from "../lib/battle-genetic-lifecycle";

const RUNNER_STATES: RunnerState[] = [
	"advance",
	"research",
	"stderr",
	"self_heal",
	"mutate",
	"retry",
	"detected",
	"blocked_handoff",
	"blocked",
	"killed",
	"promoted",
	"fastest_crash",
];

/** Frames extracted from Battle-004 mockup (HTML reference + #battle design view). */
const MARKER_FRAMES: Partial<Record<LaneEventKind, string>> = {
	killed: "marker-killed",
	blocked: "marker-blocked",
	blue_blast: "marker-blue_blast",
	detected: "marker-blue_blast",
	fastest_crash: "marker-fastest_crash",
	promoted: "marker-promoted",
	handoff: "marker-handoff",
	useful: "fx-useful",
};

export function normalizeRunnerState(state: RunnerState | string): RunnerState {
	if (RUNNER_STATES.includes(state as RunnerState)) return state as RunnerState;
	return "advance";
}

export function runnerAtlasFrame(lane: Lane): string {
	const state = normalizeRunnerState(lane.runnerState);
	if (state === "killed") return "marker-killed";
	if (state === "blocked" || state === "blocked_handoff") return "marker-blocked";
	if (state === "promoted") return "marker-promoted";
	if (state === "fastest_crash") return "marker-fastest_crash";
	if (state === "detected") return "marker-blue_blast";
	return lane.parentId ? "runner-child" : "runner-parent";
}

export function markerAtlasFrame(event: LaneEvent): string {
	if (event.geneticEffect) return geneticMarkerAtlasFrame(event.geneticEffect);
	if (isGeneticLaneEventKind(event.kind)) return geneticMarkerAtlasFrame(
		event.kind === "compile_failed" || event.kind === "method_rejected" || event.kind === "branch_abandoned"
			? "compile_error"
			: "genome_lock",
	);
	return MARKER_FRAMES[event.kind] ?? "marker-blocked";
}

export function effectAtlasFrame(kind: string): string {
	return `fx-${kind}`;
}
