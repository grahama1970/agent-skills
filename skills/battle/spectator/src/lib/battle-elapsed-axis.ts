import type { BattleNormalizedUxFixture, Lane, LaneActivitySegment, LaneEvent } from "./battle-types";

export function fixtureUsesElapsedAxis(fixture: BattleNormalizedUxFixture): boolean {
	return fixture.timeline_elapsed_axis_model?.x_position_is_elapsed_time === true;
}

export function laneElapsedRange(lane: Lane, allottedSeconds: number, useElapsed: boolean): { start: number; end: number } {
	if (useElapsed) {
		if (typeof lane.start_elapsed_seconds === "number" && typeof lane.end_elapsed_seconds === "number") {
			return { start: lane.start_elapsed_seconds, end: lane.end_elapsed_seconds };
		}
		const segments = lane.activitySegments ?? [];
		const starts = segments
			.map((segment) => segment.start_elapsed_seconds)
			.filter((value): value is number => typeof value === "number");
		const ends = segments
			.map((segment) => segment.end_elapsed_seconds)
			.filter((value): value is number => typeof value === "number");
		if (starts.length > 0 && ends.length > 0) {
			return { start: Math.min(...starts), end: Math.max(...ends) };
		}
	}
	return {
		start: (lane.xStart / 100) * allottedSeconds,
		end: (lane.xEnd / 100) * allottedSeconds,
	};
}

export function eventElapsedSeconds(event: LaneEvent, allottedSeconds: number, useElapsed: boolean): number {
	if (useElapsed) {
		if (typeof event.elapsed_seconds === "number") return event.elapsed_seconds;
		if (typeof event.at_seconds === "number") return event.at_seconds;
	}
	return (event.x / 100) * allottedSeconds;
}

export function segmentElapsedRange(
	segment: LaneActivitySegment,
	allottedSeconds: number,
	useElapsed: boolean,
): { start: number; end: number } {
	if (useElapsed) {
		if (typeof segment.start_elapsed_seconds === "number" && typeof segment.end_elapsed_seconds === "number") {
			return { start: segment.start_elapsed_seconds, end: segment.end_elapsed_seconds };
		}
	}
	return {
		start: (segment.start_x / 100) * allottedSeconds,
		end: (segment.end_x / 100) * allottedSeconds,
	};
}

export function segmentContainsPlayhead(
	segment: LaneActivitySegment,
	currentSeconds: number,
	allottedSeconds: number,
	useElapsed: boolean,
): boolean {
	const { start, end } = segmentElapsedRange(segment, allottedSeconds, useElapsed);
	return currentSeconds >= start && currentSeconds <= end;
}
