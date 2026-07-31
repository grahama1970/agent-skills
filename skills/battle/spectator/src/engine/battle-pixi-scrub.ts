import { Container, type FederatedPointerEvent, Rectangle } from "pixi.js";

/**
 * In-canvas playhead scrub. A transparent interactive layer at the bottom of the
 * timeline world converts pointer x -> seconds and reports it, replacing the DOM
 * `.playheadTrack` overlay that previously covered the well and swallowed every
 * Pixi pointer event. Markers/labels sit above this layer so their own clicks win.
 */

export type BattleScrubLayer = {
	container: Container;
	onScrub: { current: ((seconds: number) => void) | null };
	domain: { contentWidth: number; allottedSeconds: number };
	setDomain: (contentWidth: number, worldHeight: number, allottedSeconds: number) => void;
};

export function createBattleScrubLayer(): BattleScrubLayer {
	const container = new Container();
	container.label = "battle-scrub";
	container.eventMode = "static";
	container.cursor = "pointer";
	container.hitArea = new Rectangle(0, 0, 1, 1);

	const layer: BattleScrubLayer = {
		container,
		onScrub: { current: null },
		domain: { contentWidth: 1, allottedSeconds: 1 },
		setDomain(contentWidth, worldHeight, allottedSeconds) {
			this.domain.contentWidth = Math.max(1, contentWidth);
			this.domain.allottedSeconds = Math.max(1, allottedSeconds);
			this.container.hitArea = new Rectangle(0, 0, Math.max(1, contentWidth), Math.max(1, worldHeight));
		},
	};

	let dragging = false;
	const scrubTo = (event: FederatedPointerEvent) => {
		const cb = layer.onScrub.current;
		if (!cb) return;
		const localX = event.getLocalPosition(container).x;
		const seconds = Math.min(layer.domain.allottedSeconds, Math.max(0, (localX / layer.domain.contentWidth) * layer.domain.allottedSeconds));
		cb(seconds);
	};

	container.on("pointerdown", (event: FederatedPointerEvent) => {
		dragging = true;
		scrubTo(event);
	});
	container.on("globalpointermove", (event: FederatedPointerEvent) => {
		if (dragging) scrubTo(event);
	});
	const end = () => {
		dragging = false;
	};
	container.on("pointerup", end);
	container.on("pointerupoutside", end);

	return layer;
}
