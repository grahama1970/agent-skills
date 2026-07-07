import { describe, expect, it } from "vitest";
import {
	clampTimelineZoom,
	overviewViewportStyle,
	playheadLeftPx,
	scrollLeftForPlayhead,
	stepTimelineZoom,
	TIMELINE_BASE_WIDTH,
	timelineContentWidth,
} from "./timeline-playback";

describe("timeline-playback", () => {
	it("maps playhead seconds to content pixels", () => {
		expect(playheadLeftPx(60, 120, 1000)).toBe(500);
	});

	it("anchors follow-scroll like a video editor", () => {
		expect(scrollLeftForPlayhead({ playheadLeft: 800, viewportWidth: 400, scrollWidth: 1600 })).toBe(552);
	});

	it("sizes overview viewport from scroll metrics", () => {
		const style = overviewViewportStyle({ scrollLeft: 200, scrollWidth: 1000, viewportWidth: 250, trackWidth: 500 });
		expect(style.left).toBe(100);
		expect(style.width).toBe(125);
	});
});

it("clamps and steps timeline zoom like the mockup", () => {
	expect(clampTimelineZoom(3)).toBe(2);
	expect(clampTimelineZoom(0.2)).toBe(0.6);
	expect(stepTimelineZoom(1, 1)).toBe(1.15);
	expect(timelineContentWidth(2)).toBe(TIMELINE_BASE_WIDTH * 2);
});
