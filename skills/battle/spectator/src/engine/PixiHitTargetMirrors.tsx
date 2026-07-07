import type { BattleRaceEngineInput, BattleRaceEngineRowLayout, Lane, LaneEvent } from "../lib/battle-types";
import { BATTLE_LANE_LABEL_PX } from "../lib/layout-constants";
import { eventElapsedSeconds, fixtureUsesElapsedAxis, laneElapsedRange } from "../lib/battle-elapsed-axis";

type Props = {
	lanes: Lane[];
	rowLayout: BattleRaceEngineRowLayout[];
	input: BattleRaceEngineInput;
	contentWidth: number;
	allottedSeconds: number;
	scrollLeft: number;
};

function secondsToTrackPx(seconds: number, allottedSeconds: number, contentWidth: number): number {
	const safe = Math.max(1, allottedSeconds);
	return (Math.max(0, seconds) / safe) * contentWidth;
}

function laneXRange(lane: Lane, allottedSeconds: number, contentWidth: number, useElapsed: boolean) {
	const range = laneElapsedRange(lane, allottedSeconds, useElapsed);
	const start = secondsToTrackPx(range.start, allottedSeconds, contentWidth);
	const end = secondsToTrackPx(range.end, allottedSeconds, contentWidth);
	return { start, end, width: Math.max(24, end - start) };
}

export function PixiHitTargetMirrors({ lanes, rowLayout, input, contentWidth, allottedSeconds, scrollLeft }: Props) {
	const useElapsed = fixtureUsesElapsedAxis(input.fixture);
	const layoutByLane = new Map(rowLayout.map((row) => [row.laneId, row]));

	return (
		<div className="battlePixiHitMirrorLayer" aria-hidden={false}>
			{lanes.map((lane) => {
				const row = layoutByLane.get(lane.id);
				if (!row) return null;
				const { start, width } = laneXRange(lane, allottedSeconds, contentWidth, useElapsed);
				const screenX = BATTLE_LANE_LABEL_PX + start - scrollLeft;
				return (
					<button
						key={`lane-${lane.id}`}
						type="button"
						className="battlePixiHitMirror"
						data-qid={`battle:lane:${lane.id}`}
						data-qs-action="BATTLE_LANE_SELECT"
						title={`Select lane ${lane.name}`}
						aria-label={`Select lane ${lane.name}`}
						aria-pressed={input.selectedLaneId === lane.id}
						style={{
							transform: `translate(${screenX}px, ${row.topPx}px)`,
							width,
							height: row.heightPx,
						}}
						onClick={() => input.onSelectLane(lane.id)}
					/>
				);
			})}
			{lanes.flatMap((lane) => {
				const row = layoutByLane.get(lane.id);
				if (!row) return [];
				return lane.events.map((event: LaneEvent) => {
					const x = secondsToTrackPx(eventElapsedSeconds(event, allottedSeconds, useElapsed), allottedSeconds, contentWidth);
					const screenX = BATTLE_LANE_LABEL_PX + x - scrollLeft - 12;
					const eventId = event.id ?? `${lane.id}-${event.kind}-${event.x}`;
					return (
						<button
							key={`event-${eventId}`}
							type="button"
							className="pixiHitTargetMirror pixiHitTargetMirror--event"
							data-qid={`battle:marker:${lane.id}:${event.kind}`}
							data-qs-action="BATTLE_MARKER_SELECT"
							title={`Select ${event.kind} event for ${lane.name}`}
							aria-label={`${event.kind} event for ${lane.name}`}
							style={{
								transform: `translate(${screenX}px, ${row.topPx + row.heightPx / 2 - 12}px)`,
								width: 24,
								height: 24,
							}}
							onClick={() => input.onSelectEvent(eventId)}
						/>
					);
				});
			})}
		</div>
	);
}
