import type { BattleSpriteTheme, Lane, LaneEvent, PixiDisplaySpec, PixiEffectSpec } from "../lib/battle-types";
import { effectAtlasFrame, markerAtlasFrame, runnerAtlasFrame } from "./battle-race-icon-map";

function effectForKind(kind: string): PixiEffectSpec | null {
	switch (kind) {
		case "blocked":
		case "blue_blast":
			return { kind: "blocked", durationMs: 480, intensity: 1, texture: effectAtlasFrame("blocked") };
		case "killed":
			return { kind: "killed", durationMs: 520, intensity: 1, texture: effectAtlasFrame("killed") };
		case "fastest_crash":
			return { kind: "fastest_crash", durationMs: 640, intensity: 1, texture: effectAtlasFrame("fastest_crash") };
		case "promoted":
			return { kind: "promoted", durationMs: 500, intensity: 0.9, texture: effectAtlasFrame("promoted") };
		case "handoff":
		case "spawn":
			return { kind: "spawn", durationMs: 420, intensity: 0.85, texture: effectAtlasFrame("spawn") };
		case "useful":
			return { kind: "useful", durationMs: 280, intensity: 0.75, texture: effectAtlasFrame("useful") };
		default:
			return null;
	}
}

export const battleSpriteTheme: BattleSpriteTheme = {
	runnerForLane(lane: Lane): PixiDisplaySpec {
		return {
			kind: "sprite",
			texture: runnerAtlasFrame(lane),
			opacity: 1,
		};
	},
	markerForEvent(event: LaneEvent): PixiDisplaySpec {
		return {
			kind: "sprite",
			texture: markerAtlasFrame(event),
			opacity: event.proven ? 1 : 0.55,
		};
	},
	effectForEvent(event: LaneEvent): PixiEffectSpec | null {
		if (!event.proven) return null;
		return effectForKind(event.kind);
	},
};

/** @deprecated use battleSpriteTheme */
export const proceduralBattleSpriteTheme = battleSpriteTheme;
