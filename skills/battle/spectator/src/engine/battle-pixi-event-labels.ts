import { Container, Text } from "pixi.js";
import type { BattleRaceEngineRowLayout, Lane, LaneEvent } from "../lib/battle-types";
import { phaseLabelText } from "../lib/marker-labels";
import { layoutLaneEvents } from "../lib/layout-lane-events";
import { eventElapsedSeconds } from "../lib/battle-elapsed-axis";

/**
 * Progress-phase labels (RESEARCH, PAYLOAD 857, MUTATE, RED EXPLOIT…) rendered in
 * Pixi Text above/below the exploit line, matching the mockup where each dot
 * carries a phase token. Terminal icon events (blocked/killed/handoff) get the
 * marker glyph instead and are skipped here (phaseLabelText returns null for them).
 */

const TONE: Record<string, number> = {
	useful: 0xffe070,
	payload: 0xff6b7a,
	research: 0x94a3b8,
	default: 0x94a3b8,
};
const RUNNER_LABEL_CLEARANCE_PX = 92;
const DUPLICATE_LABEL_GAP_PX = 48;

function toneFor(kind: LaneEvent["kind"]): number {
	return TONE[kind] ?? TONE.default;
}

type LabelSlot = Text & { __cacheText?: string; __cacheColor?: number };

export type BattleEventLabelLayer = {
	container: Container;
	pool: LabelSlot[];
};

export function createBattleEventLabelLayer(): BattleEventLabelLayer {
	const container = new Container();
	container.label = "battle-event-labels";
	container.eventMode = "none";
	return { container, pool: [] };
}

function placeLabel(
	layer: BattleEventLabelLayer,
	writeIndex: number,
	text: string,
	color: number,
	x: number,
	y: number,
): number {
	let slot = layer.pool[writeIndex];
	if (!slot) {
		slot = new Text({ text: "", style: { fontFamily: "Inter, system-ui, sans-serif", fontSize: 9, fontWeight: "800", fill: color, letterSpacing: 0.6 } }) as LabelSlot;
		slot.anchor.set(0.5, 0.5);
		slot.eventMode = "none";
		layer.container.addChild(slot);
		layer.pool[writeIndex] = slot;
	}
	if (slot.__cacheText !== text) {
		slot.text = text;
		slot.__cacheText = text;
	}
	if (slot.__cacheColor !== color) {
		slot.style.fill = color;
		slot.__cacheColor = color;
	}
	slot.x = Math.round(x);
	slot.y = Math.round(y);
	slot.visible = true;
	return writeIndex + 1;
}

/**
 * Sync phase labels for every event past the playhead. `runnerXForLane` lets the
 * caller suppress labels colliding with the runner sprite (same rule as markers).
 */
export function syncBattleEventLabels(
	layer: BattleEventLabelLayer,
	lanes: Lane[],
	rowLayout: BattleRaceEngineRowLayout[],
	currentSeconds: number,
	allottedSeconds: number,
	contentWidth: number,
	useElapsed: boolean,
): void {
	const rowByLane = new Map(rowLayout.map((row) => [row.laneId, row]));
	let writeIndex = 0;
	const playheadX = (Math.max(0, currentSeconds) / Math.max(1, allottedSeconds)) * contentWidth;

	for (const lane of lanes) {
		const row = rowByLane.get(lane.id);
		if (!row) continue;
		const laidOut = layoutLaneEvents(lane.events, { flipBands: lane.parentId != null });
		const cy = row.topPx + row.heightPx / 2;
		const placedByText = new Map<string, number>();
		for (const event of laidOut) {
			if (event.labelBand === "none") continue;
			const text = phaseLabelText(event);
			if (!text) continue;
			const seconds = eventElapsedSeconds(event, allottedSeconds, useElapsed);
			if (seconds > currentSeconds) continue;
			const x = Math.round((Math.max(0, event.labelX) / 100) * contentWidth);
			if (Math.abs(x - playheadX) < RUNNER_LABEL_CLEARANCE_PX) continue;
			const key = `${event.labelBand}:${text}`;
			const previousX = placedByText.get(key);
			if (previousX != null && Math.abs(x - previousX) < DUPLICATE_LABEL_GAP_PX) continue;
			placedByText.set(key, x);
			const y = event.labelBand === "above" ? cy - 18 : cy + 18;
			writeIndex = placeLabel(layer, writeIndex, text, toneFor(event.kind), x, y);
		}
	}

	for (let index = writeIndex; index < layer.pool.length; index += 1) {
		layer.pool[index].visible = false;
	}
}

export function teardownBattleEventLabelLayer(layer: BattleEventLabelLayer): void {
	layer.container.destroy({ children: true });
	layer.pool.length = 0;
}
