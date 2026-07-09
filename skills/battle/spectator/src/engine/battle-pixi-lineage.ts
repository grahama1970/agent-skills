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

function lineageSignature(
	lanes: Lane[],
	rowLayout: BattleRaceEngineRowLayout[],
	collapsedParentIds: string[],
	allottedSeconds: number,
	contentWidth: number,
	useElapsed: boolean,
): string {
	return [
		...collapsedParentIds.sort(),
		...lanes.map((lane) => lane.id),
		...rowLayout.map((row) => `${row.laneId}:${row.topPx}:${row.heightPx}`),
		allottedSeconds,
		contentWidth,
		useElapsed ? "elapsed" : "track",
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
}): void {
	const { layer, lanes, rowLayout, collapsedParentIds, allottedSeconds, contentWidth, useElapsed } = args;
	const signature = lineageSignature(lanes, rowLayout, [...collapsedParentIds], allottedSeconds, contentWidth, useElapsed);
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

		const spawnSeconds = handoffSeconds(parent, allottedSeconds, useElapsed);
		if (spawnSeconds == null) continue;
		const x = secondsToWorldX(spawnSeconds, allottedSeconds, contentWidth);
		const parentY = parentRow.topPx + parentRow.heightPx / 2;

		for (const childId of childIds) {
			const child = lanes.find((lane) => lane.id === childId);
			const childRow = rowById[childId];
			if (!child || !childRow) continue;

			const childY = childRow.topPx + childRow.heightPx / 2;
			const { start } = laneElapsedRange(child, allottedSeconds, useElapsed);
			const childEntryX = secondsToWorldX(start, allottedSeconds, contentWidth);

			layer.graphics.moveTo(x, parentY);
			layer.graphics.lineTo(x, childY);
			layer.graphics.lineTo(childEntryX, childY);
			layer.graphics.stroke();
		}
	}
}

export function teardownPixiLineageLayer(layer: PixiLineageLayer): void {
	layer.graphics.clear();
	layer.signature = "";
}
