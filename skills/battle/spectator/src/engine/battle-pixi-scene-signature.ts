import type { BattleRaceEngineRowLayout, Lane } from "../lib/battle-types";
import { laneElapsedRange, segmentElapsedRange } from "../lib/battle-elapsed-axis";

export function staticTracksSignature(
	lanes: Lane[],
	rowLayout: BattleRaceEngineRowLayout[],
	allottedSeconds: number,
	contentWidth: number,
	useElapsed: boolean,
): string {
	return JSON.stringify({
		lanes: lanes.map((lane) => ({
			id: lane.id,
			segments: (lane.activitySegments ?? []).map((segment) => segmentElapsedRange(segment, allottedSeconds, useElapsed)),
			range: laneElapsedRange(lane, allottedSeconds, useElapsed),
		})),
		rows: rowLayout.map((row) => [row.laneId, row.topPx, row.heightPx]),
		allottedSeconds,
		contentWidth,
		useElapsed,
	});
}
