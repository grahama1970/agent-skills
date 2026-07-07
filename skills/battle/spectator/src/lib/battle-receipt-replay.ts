import type { BattleNormalizedUxFixture, Lane } from "./battle-types";

export const BATTLE_RECEIPT_REPLAY_FIXTURE_URL =
	"/battle-fixtures/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json";

export function battleHashPath(): string {
	if (typeof window === "undefined") return "";
	return window.location.hash.split("?")[0];
}

export function isBattleReceiptReplayView(): boolean {
	const path = battleHashPath();
	return path === "#battle/receipt" || path.startsWith("#battle/receipt/");
}

/**
 * Backend fixture diagnostic only — not a frontend gate.
 * Child visibility uses lineage.spawns[].spawn_elapsed_seconds.
 * If child_start_elapsed_seconds or lane.start_elapsed_seconds disagree with spawn time,
 * that is a backend fixture/schema defect to fix upstream.
 */
export function spawnTimingFieldsConsistent(fixture: BattleNormalizedUxFixture, childLaneId: string): boolean {
	const spawn = fixture.lineage?.spawns?.find((item) => item.child_lane_id === childLaneId);
	const spawnElapsed = spawn?.spawn_elapsed_seconds;
	if (typeof spawnElapsed !== "number") return false;
	const lane = fixture.lanes?.find((item) => item.id === childLaneId);
	const derived = [spawn?.child_start_elapsed_seconds, lane?.start_elapsed_seconds];
	return derived.every((value) => value == null || Math.abs(value - spawnElapsed) <= 0.001);
}

export function childSpawnElapsedSeconds(fixture: BattleNormalizedUxFixture, childLaneId: string): number | null {
	const spawn = fixture.lineage?.spawns?.find((item) => item.child_lane_id === childLaneId);
	if (typeof spawn?.spawn_elapsed_seconds === "number") return spawn.spawn_elapsed_seconds;

	const event = fixture.events?.find(
		(item) =>
			item.event_type === "tau.spawned_child" &&
			(item.spawned_children?.includes(childLaneId) || item.id?.includes(childLaneId)),
	);
	if (typeof event?.elapsed_seconds === "number") return event.elapsed_seconds;
	if (typeof event?.at_seconds === "number") return event.at_seconds;
	return null;
}

export function lanesVisibleAtPlayhead(
	lanes: Lane[],
	fixture: BattleNormalizedUxFixture,
	playheadSeconds: number,
): Lane[] {
	return lanes.filter((lane) => {
		if (!lane.parentId) return true;
		const spawnAt = childSpawnElapsedSeconds(fixture, lane.id);
		if (spawnAt == null) return false;
		return playheadSeconds >= spawnAt;
	});
}

export function secondsFromTimelinePointer(
	clientX: number,
	trackRect: DOMRect,
	scrollLeft: number,
	contentWidth: number,
	allottedSeconds: number,
): number {
	const x = clientX - trackRect.left + scrollLeft;
	const pct = Math.max(0, Math.min(1, x / Math.max(1, contentWidth)));
	return pct * allottedSeconds;
}

export function secondsFromOverlayTrackPointer(clientX: number, trackRect: DOMRect, allottedSeconds: number): number {
	const pct = Math.max(0, Math.min(1, (clientX - trackRect.left) / Math.max(1, trackRect.width)));
	return pct * allottedSeconds;
}
