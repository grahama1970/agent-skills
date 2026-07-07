import { scaleLinear } from "d3";

/** Lane track uses 0–100 receipt/mockup units mapped through battle time scale. */
export function laneXToMs(laneX: number, allottedMs: number) {
  return (Math.max(0, Math.min(100, laneX)) / 100) * allottedMs;
}

export function createBattleTimeScale(allottedMs: number, trackWidth: number) {
  return scaleLinear<number, number>()
    .domain([0, allottedMs])
    .range([0, Math.max(0, trackWidth)])
    .clamp(true);
}
