import type { LaneEvent } from "./battle-types";
import { phaseLabelText } from "./marker-labels";

const ICON_KINDS = new Set<LaneEvent["kind"]>([
	"blocked",
	"killed",
	"promoted",
	"fastest_crash",
	"handoff",
	"blue_blast",
	"detected",
]);

const ICON_MIN_GAP = 6;
const LABEL_CENTER_GAP = 14.5;
const ICON_CLEARANCE = 4.2;

export type LabelBand = "above" | "below" | "none";

export type LaidOutLaneEvent = LaneEvent & {
	labelBand: LabelBand;
	labelX: number;
};

export function layoutLaneEvents(events: LaneEvent[], options?: { flipBands?: boolean }): LaidOutLaneEvent[] {
	const flipBands = options?.flipBands ?? false;
	const icons = spreadIcons(events.filter((event) => isIconEvent(event)));
	const iconXs = icons.map((event) => event.x);

	const labels = events
		.filter((event) => !isIconEvent(event))
		.map((event) => ({
			...event,
			labelBand: labelBandFor(event.kind, flipBands),
			labelX: event.x,
		}));

	const above = layoutBand(
		labels.filter((event) => event.labelBand === "above"),
		iconXs,
		"above",
	);
	const below = layoutBand(
		labels.filter((event) => event.labelBand === "below"),
		iconXs,
		"below",
	);
	const byId = new Map([...above, ...below].map((event) => [event.id, event]));

	const iconRows = icons.map((event) => ({ ...event, labelBand: "none" as const, labelX: event.x }));
	const labelRows = labels.map((event) => byId.get(event.id) ?? event);
	return [...iconRows, ...labelRows];
}

export function isIconEvent(event: LaneEvent) {
	return ICON_KINDS.has(event.kind);
}

function labelBandFor(kind: LaneEvent["kind"], flipBands: boolean): LabelBand {
	if (ICON_KINDS.has(kind)) return "none";
	if (kind === "research" || kind === "payload") return flipBands ? "below" : "above";
	return flipBands ? "above" : "below";
}

function spreadIcons(events: LaneEvent[]): LaneEvent[] {
	const out = [...events].sort((a, b) => a.x - b.x);
	for (let i = 1; i < out.length; i += 1) {
		if (out[i].x - out[i - 1].x < ICON_MIN_GAP)
			out[i] = { ...out[i], x: Number((out[i - 1].x + ICON_MIN_GAP).toFixed(2)) };
	}
	return out;
}

function layoutBand(events: LaidOutLaneEvent[], iconXs: number[], band: "above" | "below"): LaidOutLaneEvent[] {
	let out = [...events].sort((a, b) => a.labelX - b.labelX);
	out = awayFromIcons(out, iconXs);
	out = spreadCenters(out);
	if (band === "below") out = layoutBottom(out, iconXs);
	out = awayFromIcons(out, iconXs);
	return spreadCenters(out);
}

function awayFromIcons(events: LaidOutLaneEvent[], iconXs: number[]): LaidOutLaneEvent[] {
	return events.map((event) => {
		let labelX = event.labelX;
		for (const iconX of iconXs) {
			if (Math.abs(labelX - iconX) < ICON_CLEARANCE) labelX = iconX - ICON_CLEARANCE;
		}
		return { ...event, labelX: Math.max(0, Number(labelX.toFixed(2))) };
	});
}

function layoutBottom(events: LaidOutLaneEvent[], iconXs: number[]): LaidOutLaneEvent[] {
	return events.map((event) => {
		let labelX = event.labelX;
		for (const iconX of iconXs) {
			if (Math.abs(labelX - iconX) < 1.2) labelX = iconX + ICON_MIN_GAP * 0.55;
		}
		return { ...event, labelX: Number(labelX.toFixed(2)) };
	});
}

function spreadCenters(events: LaidOutLaneEvent[]): LaidOutLaneEvent[] {
	const out = events.map((event) => ({ ...event }));
	for (let i = 1; i < out.length; i += 1) {
		const prevWidth = estimateCenterGap(out[i - 1]);
		const nextWidth = estimateCenterGap(out[i]);
		const minX = out[i - 1].labelX + Math.max(LABEL_CENTER_GAP, (prevWidth + nextWidth) * 0.5);
		if (out[i].labelX < minX) out[i] = { ...out[i], labelX: Number(minX.toFixed(2)) };
	}
	return out;
}

function estimateCenterGap(event: LaidOutLaneEvent) {
	const text = phaseLabelText(event) ?? "EVENT";
	return Math.max(10, Math.min(16, 6 + text.length * 0.45));
}
