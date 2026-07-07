import type { Lane } from "./battle-types";
import { trackPct } from "./utils";

/** Spawn-at-event branch: vertical at parent handoff, horizontal into child lane. */
export type LineageSpawnBranch = {
	parentId: string;
	childId: string;
	x: number;
	parentY: number;
	childY: number;
	childEntryX: number;
};

type RowRect = {
	id: string;
	top: number;
	height: number;
	trackLeft: number;
	trackWidth: number;
};

export function handoffTimelineX(lane: Lane | undefined): number | null {
	if (!lane) return null;
	const handoff = lane.events.find((event) => event.kind === "handoff");
	if (handoff) return handoff.x;
	return Number((lane.xEnd * 0.72).toFixed(2));
}

function trackX(rect: RowRect, timelineX: number) {
	return rect.trackLeft + (trackPct(timelineX) / 100) * rect.trackWidth;
}

export function computeLineageLayout({
	lanes,
	rowRects,
	collapsed,
	containerTop,
}: {
	lanes: Lane[];
	rowRects: RowRect[];
	collapsed: Set<string>;
	containerTop: number;
}): { branches: LineageSpawnBranch[] } {
	const rectById = Object.fromEntries(rowRects.map((row) => [row.id, row]));
	const branches: LineageSpawnBranch[] = [];

	for (const parent of lanes) {
		const childIds = parent.children?.length
			? parent.children
			: lanes.filter((lane) => lane.parentId === parent.id).map((lane) => lane.id);
		if (!childIds.length || collapsed.has(parent.id)) continue;

		const parentRect = rectById[parent.id];
		if (!parentRect) continue;

		const spawnX = handoffTimelineX(parent) ?? parent.xEnd * 0.72;
		const x = trackX(parentRect, spawnX);
		const parentY = parentRect.top - containerTop + parentRect.height * 0.5;

		for (const childId of childIds) {
			const childRect = rectById[childId];
			const child = lanes.find((lane) => lane.id === childId);
			if (!childRect || !child) continue;

			branches.push({
				parentId: parent.id,
				childId: child.id,
				x,
				parentY,
				childY: childRect.top - containerTop + childRect.height * 0.5,
				childEntryX: trackX(childRect, child.xStart),
			});
		}
	}

	return { branches };
}
