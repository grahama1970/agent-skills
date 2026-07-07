import { useBattleTimelineScale } from "./BattleTimelineProvider";

/** Lane track uses 0–100 receipt/mockup units mapped through D3 time scale. */
export function useBattleTimelineCoords(allottedSeconds: number) {
  const {
    allottedMs,
    leftPxFromLaneX,
    leftPxFromMs,
    msFromLaneX,
    secondsFromLaneX,
    trackWidth,
  } = useBattleTimelineScale();

  const expectedMs = Math.max(1, allottedSeconds) * 1000;
  if (expectedMs !== allottedMs && process.env.NODE_ENV !== "production") {
    console.warn(
      `useBattleTimelineCoords allottedSeconds (${allottedSeconds}) does not match provider (${allottedMs / 1000})`
    );
  }

  return {
    leftPxFromLaneX,
    leftPxFromMs,
    msFromLaneX,
    secondsFromLaneX,
    valueToPixels: leftPxFromMs,
    allottedMs,
    trackWidth,
  };
}
