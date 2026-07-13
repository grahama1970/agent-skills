import { Container, Graphics } from "pixi.js";
import type { BattleRaceEngineRowLayout, Lane } from "../lib/battle-types";
import { eventElapsedSeconds, fixtureUsesElapsedAxis, laneElapsedRange } from "../lib/battle-elapsed-axis";
import { configureBattleSceneLayer } from "./battle-pixi-game-mechanics";

export type PixiLineageLayer = {
	container: Container;
	graphics: Graphics;
	signature: string;
};

export function createPixiLineageLayer(): PixiLineageLayer {
	const container = configureBattleSceneLayer(new Container(), { label: "battle-lineage", cullable: true });
	const graphics = new Graphics();
	graphics.label = "battle-lineage-branches";
	container.addChild(graphics);
	return { container, graphics, signature: "" };
}

function secondsToWorldX(seconds: number, allottedSeconds: number, contentWidth: number): number {
	return (Math.max(0, seconds) / Math.max(1, allottedSeconds)) * contentWidth;
}

function handoffSeconds(lane: Lane, allottedSeconds: number, useElapsed: boolean): number | null {
	const handoff = lane.events.find((event) => event.kind === "handoff" && event.proven);
	if (handoff) return eventElapsedSeconds(handoff, allottedSeconds, useElapsed);
	const { end } = laneElapsedRange(lane, allottedSeconds, useElapsed);
	return end * 0.72;
}

function childEntrySeconds(child: Lane, allottedSeconds: number, useElapsed: boolean): number {
	if (useElapsed && typeof child.visible_from_elapsed_seconds === "number") return child.visible_from_elapsed_seconds;
	return laneElapsedRange(child, allottedSeconds, useElapsed).start;
}

export function childLineageMotion(args: {
	lane: Lane;
	lanes: Lane[];
	rowLayout: BattleRaceEngineRowLayout[];
	currentSeconds: number;
	allottedSeconds: number;
	contentWidth: number;
	useElapsed: boolean;
}): { x: number; y: number; alpha: number } | null {
	const { lane, lanes, rowLayout, currentSeconds, allottedSeconds, contentWidth, useElapsed } = args;
	if (!lane.parentId) return null;
	const parent = lanes.find((item) => item.id === lane.parentId);
	const parentRow = rowLayout.find((item) => item.laneId === lane.parentId);
	const childRow = rowLayout.find((item) => item.laneId === lane.id);
	if (!parent || !parentRow || !childRow) return null;
	const visibleAt = childEntrySeconds(lane, allottedSeconds, useElapsed);
	const activeAt = lane.first_active_segment_elapsed_seconds ?? visibleAt;
	if (currentSeconds < visibleAt || currentSeconds > activeAt + 1.5) return null;
	const spawnX = secondsToWorldX(visibleAt, allottedSeconds, contentWidth);
	const parentY = parentRow.topPx + parentRow.heightPx / 2;
	const childY = childRow.topPx + childRow.heightPx / 2;
	if (currentSeconds < activeAt) return { x: spawnX + 10, y: parentY + 8, alpha: 0.42 };
	const progress = Math.max(0, Math.min(1, (currentSeconds - activeAt) / 1.5));
	const landingHop = Math.sin(progress * Math.PI) * 16;
	return {
		x: spawnX + progress * 24,
		y: parentY + (childY - parentY) * progress - landingHop,
		alpha: 1,
	};
}

export function lineageTransitionPhase(lane: Lane, currentSeconds: number): "hidden" | "authorized_pending" | "descending" | "active" {
	if (!lane.parentId) return "active";
	const visibleAt = lane.visible_from_elapsed_seconds ?? lane.start_elapsed_seconds ?? Number.POSITIVE_INFINITY;
	const activeAt = lane.first_active_segment_elapsed_seconds ?? visibleAt;
	if (currentSeconds < visibleAt) return "hidden";
	if (currentSeconds < activeAt) return "authorized_pending";
	if (currentSeconds <= activeAt + 1.5) return "descending";
	return "active";
}

function lineageSignature(
	lanes: Lane[],
	rowLayout: BattleRaceEngineRowLayout[],
	collapsedParentIds: string[],
	allottedSeconds: number,
	contentWidth: number,
	useElapsed: boolean,
	currentSeconds: number,
): string {
	return [
		...collapsedParentIds.sort(),
		...lanes.map((lane) => lane.id),
		...rowLayout.map((row) => `${row.laneId}:${row.topPx}:${row.heightPx}`),
		allottedSeconds,
		contentWidth,
		useElapsed ? "elapsed" : "track",
		currentSeconds.toFixed(2),
	].join("|");
}

export function syncPixiLineage(args: {
	layer: PixiLineageLayer;
	lanes: Lane[];
	rowLayout: BattleRaceEngineRowLayout[];
	collapsedParentIds: Set<string>;
	allottedSeconds: number;
	contentWidth: number;
	useElapsed: boolean;
	currentSeconds: number;
}): void {
	const { layer, lanes, rowLayout, collapsedParentIds, allottedSeconds, contentWidth, useElapsed, currentSeconds = 0 } = args;
	const signature = lineageSignature(lanes, rowLayout, [...collapsedParentIds], allottedSeconds, contentWidth, useElapsed, currentSeconds);
	if (signature === layer.signature) return;
	layer.signature = signature;

	const rowById = Object.fromEntries(rowLayout.map((row) => [row.laneId, row]));
	layer.graphics.clear();
	layer.graphics.setStrokeStyle({ width: 2, color: 0x38bdf8, alpha: 0.55 });

	for (const parent of lanes) {
		const childIds = parent.children?.length
			? parent.children
			: lanes.filter((lane) => lane.parentId === parent.id).map((lane) => lane.id);
		if (!childIds.length || collapsedParentIds.has(parent.id)) continue;

		const parentRow = rowById[parent.id];
		if (!parentRow) continue;

		const parentY = parentRow.topPx + parentRow.heightPx / 2;

		for (const childId of childIds) {
			const child = lanes.find((lane) => lane.id === childId);
			const childRow = rowById[childId];
			if (!child || !childRow) continue;

			const childY = childRow.topPx + childRow.heightPx / 2;
			const spawnSeconds = childEntrySeconds(child, allottedSeconds, useElapsed) ?? handoffSeconds(parent, allottedSeconds, useElapsed);
			if (spawnSeconds == null) continue;
			const x = secondsToWorldX(spawnSeconds, allottedSeconds, contentWidth);
			const childEntryX = x;

			layer.graphics.moveTo(x, parentY);
			layer.graphics.lineTo(x, childY);
			layer.graphics.lineTo(childEntryX, childY);
			layer.graphics.stroke();

			const activeAt = child.first_active_segment_elapsed_seconds ?? spawnSeconds;
			if (currentSeconds >= spawnSeconds && currentSeconds <= activeAt + 1.5) {
				layer.graphics.setStrokeStyle({ width: 3, color: 0xa3e635, alpha: 0.9 });
				layer.graphics.moveTo(x - 9, parentY);
				layer.graphics.lineTo(x - 9, childY);
				layer.graphics.moveTo(x + 9, parentY);
				layer.graphics.lineTo(x + 9, childY);
				for (let rungY = parentY + 10; rungY < childY; rungY += 12) {
					layer.graphics.moveTo(x - 9, rungY);
					layer.graphics.lineTo(x + 9, rungY);
				}
				layer.graphics.stroke();
				const packetEvent = child.events.find((event) => event.label === "KNOWLEDGE TRANSFER");
				const packetAt = packetEvent ? eventElapsedSeconds(packetEvent, allottedSeconds, useElapsed) : spawnSeconds;
				if (currentSeconds >= packetAt && currentSeconds < activeAt) {
					const progress = Math.max(0, Math.min(1, (currentSeconds - packetAt) / Math.max(0.001, activeAt - packetAt)));
					layer.graphics.circle(x, parentY + (childY - parentY) * progress, 5).fill({ color: 0x22d3ee, alpha: 0.95 });
				}
				layer.graphics.setStrokeStyle({ width: 2, color: 0x38bdf8, alpha: 0.55 });
			}
		}
	}
}

export function teardownPixiLineageLayer(layer: PixiLineageLayer): void {
	layer.graphics.clear();
	layer.signature = "";
}
