import type { Lane } from "./battle-types";

export const TIMELINE_BASE_WIDTH = 1320;
export const PLAYHEAD_SCROLL_ANCHOR = 0.62;

export const TIMELINE_ZOOM_MIN = 0.6;
export const TIMELINE_ZOOM_MAX = 2;
export const TIMELINE_ZOOM_STEP = 0.15;
export const TIMELINE_ZOOM_DEFAULT = 1;

export function clampTimelineZoom(value: number) {
	return Math.max(TIMELINE_ZOOM_MIN, Math.min(TIMELINE_ZOOM_MAX, Number(value.toFixed(2))));
}

export function stepTimelineZoom(value: number, direction: 1 | -1) {
	return clampTimelineZoom(value + direction * TIMELINE_ZOOM_STEP);
}

export function timelineContentWidth(zoom: number) {
	return Math.round(TIMELINE_BASE_WIDTH * clampTimelineZoom(zoom));
}

export function playheadRatio(seconds: number, allottedSeconds: number) {
	if (!allottedSeconds) return 0;
	return Math.max(0, Math.min(1, seconds / allottedSeconds));
}

export function playheadLeftPx(seconds: number, allottedSeconds: number, contentWidth: number) {
	return playheadRatio(seconds, allottedSeconds) * contentWidth;
}

export function scrollLeftForPlayhead({
	playheadLeft,
	viewportWidth,
	scrollWidth,
	anchor = PLAYHEAD_SCROLL_ANCHOR,
}: {
	playheadLeft: number;
	viewportWidth: number;
	scrollWidth: number;
	anchor?: number;
}) {
	const maxScroll = Math.max(0, scrollWidth - viewportWidth);
	const target = playheadLeft - viewportWidth * anchor;
	return Math.max(0, Math.min(maxScroll, target));
}

export function overviewViewportStyle({
	scrollLeft,
	scrollWidth,
	viewportWidth,
	trackWidth,
}: {
	scrollLeft: number;
	scrollWidth: number;
	viewportWidth: number;
	trackWidth: number;
}) {
	if (scrollWidth <= viewportWidth) {
		return { left: 0, width: trackWidth };
	}
	const width = Math.max(18, (viewportWidth / scrollWidth) * trackWidth);
	const left = (scrollLeft / scrollWidth) * trackWidth;
	return { left, width };
}

export type TimelineOverviewMark = {
	id: string;
	leftPct: number;
	tone: "crash" | "promoted" | "blocked";
	title: string;
};

export function overviewMarksFromLanes(lanes: Lane[], allottedSeconds: number): TimelineOverviewMark[] {
	const marks: TimelineOverviewMark[] = [];
	for (const lane of lanes) {
		const terminal = lane.terminal;
		if (terminal === "none") continue;
		const anchorEvent =
			lane.events.find(
				(event) => event.kind === "fastest_crash" || event.kind === "promoted" || event.kind === "blocked",
			) ?? lane.events[lane.events.length - 1];
		const x = anchorEvent?.x ?? lane.runnerX ?? lane.xEnd;
		marks.push({
			id: `${lane.id}:${terminal}`,
			leftPct: playheadRatio(x, 100) * 100,
			tone: terminal === "fastest_crash" ? "crash" : terminal === "promoted" ? "promoted" : "blocked",
			title: `${lane.name} · ${terminal}`,
		});
	}
	return marks;
}
