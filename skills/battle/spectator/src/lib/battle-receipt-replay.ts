import type { BattleNormalizedUxFixture, Lane } from "./battle-types";

export const BATTLE_RECEIPT_REPLAY_FIXTURE_URL =
	"/battle-fixtures/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json";

export const BATTLE_SPARSE_REPLAY_FIXTURE_URL =
	"/battle-fixtures/battle-004-sparse-pixi-replay/battle.normalized_ux_fixture.json";

export const BATTLE_RECEIPT_REPLAY_FIXTURE_URLS = {
	"battle-004-parent-spawn": BATTLE_RECEIPT_REPLAY_FIXTURE_URL,
	"battle-005-ssrf-metadata": "/battle-fixtures/battle-005-ssrf-metadata-pixi-replay/battle.normalized_ux_fixture.json",
	"battle-006-pickle-deserialization": "/battle-fixtures/battle-006-pickle-deserialization-pixi-replay/battle.normalized_ux_fixture.json",
	"battle-007-file-upload": "/battle-fixtures/battle-007-file-upload-pixi-replay/battle.normalized_ux_fixture.json",
	"battle-004-kill-shot": "/battle-fixtures/battle-004-kill-shot-pixi-replay/battle.normalized_ux_fixture.json",
} as const;

export type BattleReceiptReplayFixtureKey = keyof typeof BATTLE_RECEIPT_REPLAY_FIXTURE_URLS;

export function battleHashPath(): string {
	if (typeof window === "undefined") return "";
	return window.location.hash.split("?")[0];
}

export function isBattleReceiptReplayView(): boolean {
	const path = battleHashPath();
	return path === "#battle/receipt" || path.startsWith("#battle/receipt/");
}

export function battleHashSearchParams(hash: string): URLSearchParams {
	const query = hash.includes("?") ? hash.slice(hash.indexOf("?") + 1) : "";
	return new URLSearchParams(query);
}

export function battleReceiptReplayFixtureKey(hash: string): BattleReceiptReplayFixtureKey {
	const requested = battleHashSearchParams(hash).get("fixture") ?? "battle-004-parent-spawn";
	return requested in BATTLE_RECEIPT_REPLAY_FIXTURE_URLS ? (requested as BattleReceiptReplayFixtureKey) : "battle-004-parent-spawn";
}

export function battleReceiptReplayFixtureUrl(hash: string): string {
	return BATTLE_RECEIPT_REPLAY_FIXTURE_URLS[battleReceiptReplayFixtureKey(hash)];
}

function nearlyEqual(a: number, b: number): boolean {
	return Math.abs(a - b) <= 0.001;
}

/**
 * Backend fixture diagnostic only — not a frontend gate.
 * Validates split spawn semantics after backend schema correction:
 * visibility (visible_from/spawn_elapsed) vs first active segment timing.
 */
export function spawnTimingFieldsConsistent(fixture: BattleNormalizedUxFixture, childLaneId: string): boolean {
	const spawn = fixture.lineage?.spawns?.find((item) => item.child_lane_id === childLaneId);
	const spawnElapsed = spawn?.spawn_elapsed_seconds;
	const visibleFrom = spawn?.visible_from_elapsed_seconds ?? spawnElapsed;
	if (typeof spawnElapsed !== "number" || typeof visibleFrom !== "number") return false;
	if (!nearlyEqual(visibleFrom, spawnElapsed)) return false;

	const firstActive = spawn?.first_active_segment_elapsed_seconds ?? spawn?.child_start_elapsed_seconds;
	if (typeof firstActive === "number" && typeof spawn?.child_start_elapsed_seconds === "number") {
		if (!nearlyEqual(firstActive, spawn.child_start_elapsed_seconds)) return false;
	}

	const lane = fixture.lanes?.find((item) => item.id === childLaneId);
	if (typeof lane?.visible_from_elapsed_seconds === "number" && !nearlyEqual(lane.visible_from_elapsed_seconds, visibleFrom)) {
		return false;
	}
	if (typeof lane?.start_elapsed_seconds === "number" && !nearlyEqual(lane.start_elapsed_seconds, visibleFrom)) {
		return false;
	}
	if (
		typeof lane?.first_active_segment_elapsed_seconds === "number" &&
		typeof firstActive === "number" &&
		!nearlyEqual(lane.first_active_segment_elapsed_seconds, firstActive)
	) {
		return false;
	}
	return true;
}

/** Phase 1 child lane visibility gate — receipt-backed spawn visibility time. */
export function childSpawnElapsedSeconds(fixture: BattleNormalizedUxFixture, childLaneId: string): number | null {
	const spawn = fixture.lineage?.spawns?.find((item) => item.child_lane_id === childLaneId);
	if (spawn) {
		const visibleFrom = spawn.visible_from_elapsed_seconds ?? spawn.spawn_elapsed_seconds;
		if (typeof visibleFrom === "number") return visibleFrom;
	}

	const lane = fixture.lanes?.find((item) => item.id === childLaneId && item.parentId);
	if (typeof lane?.visible_from_elapsed_seconds === "number") return lane.visible_from_elapsed_seconds;

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
