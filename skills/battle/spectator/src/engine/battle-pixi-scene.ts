import { AnimatedSprite, Container, Graphics, Sprite, type Spritesheet, type Texture } from "pixi.js";
import type { BattleRaceEngineInput, BattleRaceEngineRowLayout, Lane, LaneActivitySegment, LaneEvent } from "../lib/battle-types";
import { textureFromAtlas } from "./battle-race-atlas";
import { runnerAnimationTextures, runnerSpriteAnchor, runnerSpritesheet, type BattleRunnerAnimation, type BattleRunnerSpriteId } from "./battle-runner-sprites";
import {
	activitySegmentAtPlayhead,
	animationSpeedFor,
	isProvisionalSegment,
	runnerAnimationWithReceiptGate,
} from "./battle-runner-animation";
import { spriteIdForLane } from "./battle-lane-variant-map";
import { battleSpriteTheme } from "./battle-sprite-theme";
import { configureBattleSceneLayer, updateWorldCullArea } from "./battle-pixi-game-mechanics";
import { pixiAllowsTerminalEffect, pixiReceiptValidationGate } from "./battle-pixi-validation";
import {
	eventElapsedSeconds,
	fixtureUsesElapsedAxis,
	laneElapsedRange,
	segmentElapsedRange,
} from "../lib/battle-elapsed-axis";
import { staticTracksSignature } from "./battle-pixi-scene-signature";
import {
	KILL_SHOT_IMPACT_SECONDS,
	KILL_SHOT_TRAVEL_SECONDS,
	createKillShotLayer,
	killShotVisualForEvent,
	syncKillShots,
	resolveKillShotImpact,
	teardownKillShotLayer,
	type KillShotLayer,
	type KillShotVisual,
} from "./battle-pixi-kill-shot";
import { childLineageMotion, createPixiLineageLayer, syncPixiLineage, teardownPixiLineageLayer, type PixiLineageLayer } from "./battle-pixi-lineage";
import { hasLucideMarker, lucideMarkerGraphic } from "./battle-lucide-markers";
import { createBattleEventLabelLayer, syncBattleEventLabels, teardownBattleEventLabelLayer, type BattleEventLabelLayer } from "./battle-pixi-event-labels";
import {
	createBeatVfxLayer,
	syncBeatEmphasisVfx,
	teardownBeatVfxLayer,
	type BeatVfxLayer,
} from "./battle-pixi-beat-vfx";

export type RunnerActor = {
	sprite: AnimatedSprite;
	variantId: BattleRunnerSpriteId;
	animation: BattleRunnerAnimation;
};

export type BattlePixiSceneLayers = {
	world: Container;
	tracksStatic: Graphics;
	tracksPlayhead: Graphics;
	markers: Container;
	lineage: PixiLineageLayer;
	killShots: KillShotLayer;
	beatVfx: BeatVfxLayer;
	runners: Container;
	eventLabels: BattleEventLabelLayer;
	markerPool: Sprite[];
	lucideMarkerPool: Graphics[];
	// Current event-selection callback; markers dispatch to it on pointertap.
	onSelectEvent: { current: (eventId: string) => void };
};

type SelectableMarker = { __eventId?: string; eventMode: string; cursor: string; on: (event: string, fn: () => void) => void };

/** Make a pooled marker clickable once; it reports its current __eventId on tap. */
function bindMarkerSelection(marker: SelectableMarker, layers: BattlePixiSceneLayers): void {
	marker.eventMode = "static";
	marker.cursor = "pointer";
	marker.on("pointertap", () => {
		if (marker.__eventId) layers.onSelectEvent.current(marker.__eventId);
	});
}

export type BattlePixiSceneRuntime = BattlePixiSceneLayers & {
	tracksSignature: string;
};

function secondsToWorldX(seconds: number, allottedSeconds: number, contentWidth: number): number {
	return (Math.max(0, seconds) / Math.max(1, allottedSeconds)) * contentWidth;
}

function runnerXAtPlayhead(
	lane: Lane,
	currentSeconds: number,
	allottedSeconds: number,
	contentWidth: number,
	useElapsed: boolean,
): number {
	const { start, end } = laneElapsedRange(lane, allottedSeconds, useElapsed);
	if (currentSeconds <= start) return secondsToWorldX(start, allottedSeconds, contentWidth);
	if (currentSeconds >= end) return secondsToWorldX(end, allottedSeconds, contentWidth);
	return secondsToWorldX(currentSeconds, allottedSeconds, contentWidth);
}

export function createBattlePixiSceneLayers(): BattlePixiSceneRuntime {
	const world = configureBattleSceneLayer(new Container(), { label: "battle-world", cullable: false });
	const tracksStatic = new Graphics();
	const tracksPlayhead = new Graphics();
	configureBattleSceneLayer(tracksStatic, { label: "battle-tracks-static", cullable: false });
	configureBattleSceneLayer(tracksPlayhead, { label: "battle-tracks-playhead", cullable: false });
	const markers = configureBattleSceneLayer(new Container(), { label: "battle-markers", cullable: false });
	markers.interactiveChildren = true; // event markers are clickable (select the lane)
	const lineage = createPixiLineageLayer();
	const killShots = createKillShotLayer();
	const beatVfx = createBeatVfxLayer();
	const runners = configureBattleSceneLayer(new Container(), { label: "battle-runners", cullable: false });
	const eventLabels = createBattleEventLabelLayer();
	world.addChild(tracksStatic);
	world.addChild(markers);
	// Exploit-progress line draws ABOVE the event markers so it reads as one
	// continuous line with dots on it (mockup), instead of the marker sprites'
	// opaque centers breaking the line.
	world.addChild(tracksPlayhead);
	world.addChild(eventLabels.container);
	world.addChild(lineage.container);
	world.addChild(killShots.container);
	world.addChild(beatVfx.container);
	world.addChild(runners);
	return { world, tracksStatic, tracksPlayhead, markers, lineage, killShots, beatVfx, runners, eventLabels, markerPool: [], lucideMarkerPool: [], onSelectEvent: { current: () => {} }, tracksSignature: "" };
}

function drawDashedSegment(graphics: Graphics, x0: number, x1: number, y: number, dash = 8, gap = 6) {
	let x = x0;
	while (x < x1) {
		const end = Math.min(x1, x + dash);
		graphics.moveTo(x, y);
		graphics.lineTo(end, y);
		x = end + gap;
	}
}

function drawSegmentLine(
	graphics: Graphics,
	segment: LaneActivitySegment,
	y: number,
	contentWidth: number,
	allottedSeconds: number,
	useElapsed: boolean,
	provisional: boolean,
) {
	const range = segmentElapsedRange(segment, allottedSeconds, useElapsed);
	const x0 = secondsToWorldX(range.start, allottedSeconds, contentWidth);
	const x1 = secondsToWorldX(range.end, allottedSeconds, contentWidth);
	if (provisional) {
		graphics.setStrokeStyle({ width: 2, color: 0x64748b, alpha: 0.45 });
		drawDashedSegment(graphics, x0, x1, y);
		graphics.stroke();
		return;
	}
	graphics.setStrokeStyle({ width: 2, color: 0x334155, alpha: 0.95 });
	graphics.moveTo(x0, y);
	graphics.lineTo(x1, y);
	graphics.stroke();
}

function drawStaticTracks(
	graphics: Graphics,
	lanes: Lane[],
	rowLayout: BattleRaceEngineRowLayout[],
	allottedSeconds: number,
	contentWidth: number,
	useElapsed: boolean,
) {
	graphics.clear();
	for (const lane of lanes) {
		const row = rowLayout.find((item) => item.laneId === lane.id);
		if (!row) continue;
		// Single rounded source of truth for the row's vertical center — must match
		// the marker sprite y (placePooledMarker rounds too) so the line and the
		// intervention icons snap to the same whole pixel (no anti-aliased step).
		const y = Math.round(row.topPx + row.heightPx / 2);
		const { start, end } = laneElapsedRange(lane, allottedSeconds, useElapsed);
		const x0 = secondsToWorldX(start, allottedSeconds, contentWidth);
		const x1 = secondsToWorldX(end, allottedSeconds, contentWidth);

		graphics.setStrokeStyle({ width: 1, color: 0x0f172a, alpha: 0.85 });
		graphics.moveTo(x0, y);
		graphics.lineTo(x1, y);
		graphics.stroke();

		const segments = lane.activitySegments ?? [];
		if (segments.length > 0) {
			for (const segment of segments) {
				drawSegmentLine(graphics, segment, y, contentWidth, allottedSeconds, useElapsed, isProvisionalSegment(segment));
			}
		} else {
			graphics.setStrokeStyle({ width: 2, color: 0x1e293b, alpha: 0.9 });
			graphics.moveTo(x0, y);
			graphics.lineTo(x1, y);
			graphics.stroke();
		}
	}
}

function drawPlayheadTracks(
	graphics: Graphics,
	lanes: Lane[],
	rowLayout: BattleRaceEngineRowLayout[],
	allottedSeconds: number,
	contentWidth: number,
	currentSeconds: number,
	useElapsed: boolean,
) {
	graphics.clear();
	for (const lane of lanes) {
		const row = rowLayout.find((item) => item.laneId === lane.id);
		if (!row) continue;
		const y = Math.round(row.topPx + row.heightPx / 2);
		const { start, end } = laneElapsedRange(lane, allottedSeconds, useElapsed);
		const x0 = secondsToWorldX(start, allottedSeconds, contentWidth);
		const x1 = secondsToWorldX(end, allottedSeconds, contentWidth);
		const playheadX = runnerXAtPlayhead(lane, currentSeconds, allottedSeconds, contentWidth, useElapsed);
		if (playheadX > x0) {
			graphics.setStrokeStyle({ width: 3, color: 0xef4444, alpha: 0.55 });
			graphics.moveTo(x0, y);
			graphics.lineTo(Math.min(playheadX, x1), y);
			graphics.stroke();
		}
	}

	const playheadX = secondsToWorldX(currentSeconds, allottedSeconds, contentWidth);
	const maxY = rowLayout.reduce((max, row) => Math.max(max, row.topPx + row.heightPx), 0);
	// Ghost playhead: faint neutral line so it provides the global time axis without
	// visually competing with the sprites/lineage lines (DAW-style muted playhead).
	graphics.setStrokeStyle({ width: 1, color: 0xc9d1d9, alpha: 0.15 });
	graphics.moveTo(playheadX, 0);
	graphics.lineTo(playheadX, maxY);
	graphics.stroke();
}

function placePooledMarker(
	pool: Sprite[],
	container: Container,
	writeIndex: number,
	texture: Texture | undefined,
	x: number,
	y: number,
	alpha: number,
	scale = 1,
	selection?: { eventId: string; layers: BattlePixiSceneLayers },
): number {
	if (!texture) return writeIndex;
	let sprite = pool[writeIndex] as (Sprite & { __eventId?: string }) | undefined;
	if (!sprite) {
		sprite = new Sprite({ anchor: 0.5, eventMode: "none" });
		sprite.cullable = true;
		container.addChild(sprite);
		pool[writeIndex] = sprite;
	}
	sprite.texture = texture;
	sprite.x = Math.round(x);
	sprite.y = Math.round(y);
	sprite.alpha = alpha;
	sprite.scale.set(scale);
	sprite.visible = true;
	// Event markers are clickable (select the lane); transient effect sprites are not.
	sprite.__eventId = selection?.eventId;
	if (selection) {
		if (sprite.eventMode === "none") bindMarkerSelection(sprite as unknown as SelectableMarker, selection.layers);
	} else if (sprite.eventMode !== "none") {
		sprite.eventMode = "none";
	}
	return writeIndex + 1;
}

function hideUnusedMarkers(pool: Sprite[], usedCount: number) {
	for (let index = usedCount; index < pool.length; index += 1) {
		pool[index].visible = false;
	}
}

type PooledLucide = Graphics & { __markerKind?: LaneEvent["kind"] };

/** Place a pooled lucide-vector marker (shared GraphicsContext) at (x,y). */
function placePooledLucideMarker(
	pool: Graphics[],
	container: Container,
	writeIndex: number,
	kind: LaneEvent["kind"],
	x: number,
	y: number,
	alpha: number,
	scale: number,
	selection?: { eventId: string; layers: BattlePixiSceneLayers },
): number {
	let graphic = pool[writeIndex] as (PooledLucide & { __eventId?: string }) | undefined;
	if (!graphic || graphic.__markerKind !== kind) {
		if (graphic) graphic.destroy({ context: false });
		const created = lucideMarkerGraphic(kind) as (PooledLucide & { __eventId?: string }) | null;
		if (!created) return writeIndex;
		created.__markerKind = kind;
		container.addChild(created);
		pool[writeIndex] = created;
		graphic = created;
		if (selection) bindMarkerSelection(graphic as unknown as SelectableMarker, selection.layers);
	}
	graphic.x = Math.round(x);
	graphic.y = Math.round(y);
	graphic.alpha = alpha;
	graphic.scale.set(scale);
	graphic.visible = true;
	graphic.__eventId = selection?.eventId;
	return writeIndex + 1;
}

function hideUnusedGraphics(pool: Graphics[], usedCount: number) {
	for (let index = usedCount; index < pool.length; index += 1) {
		pool[index].visible = false;
	}
}


/** Readable in-lane runners — match design row band without 95% pile-up. */
export function runnerDisplayScale(rowHeightPx: number): number {
	// Pixel-art crispness (WebGPT design review 2026-07-23): use an INTEGER display
	// scale so the 64px atlas frame maps 1:1 to device pixels — fractional resampling
	// is what made the runners look rough/soft. The 64px frame already pads the
	// character to ~50px visible, which sits cleanly baseline-inset in a 68-84px row.
	if (rowHeightPx >= 120) return 2;
	if (rowHeightPx >= 56) return 1;
	return 0.5;
}

/**
 * Lane-event marker icons (skull / shield / lightbulb / rocket, per the legend) render
 * from ~36–40px atlas frames. At scale 1 they read far smaller than the ~72px runners in
 * a 92px row and look like faint dots. Scale them up to a readable band (target ~44–52px)
 * so they match the mockup's prominent per-event icons. Marker textures average ~40px.
 */
export function markerDisplayScale(rowHeightPx: number): number {
	const targetPx = Math.max(44, Math.min(52, Math.max(24, rowHeightPx) * 0.55));
	return targetPx / 40;
}

function clampRunnerX(
	x: number,
	contentWidth: number,
	rowHeightPx: number,
	variantId: BattleRunnerSpriteId,
): number {
	const framePx = 64;
	const scale = runnerDisplayScale(rowHeightPx);
	const anchorX = Math.max(0, Math.min(1, runnerSpriteAnchor(variantId).x));
	const leftExtent = framePx * scale * anchorX;
	const rightExtent = framePx * scale * (1 - anchorX);
	const edgePaddingPx = 12;
	const minX = leftExtent + edgePaddingPx;
	const maxX = contentWidth - rightExtent - edgePaddingPx;
	if (maxX < minX) return contentWidth / 2;
	return Math.max(minX, Math.min(maxX, x));
}

function upsertRunnerActor(args: {
	runners: Container;
	runnerMap: Map<string, RunnerActor>;
	laneId: string;
	variantId: BattleRunnerSpriteId;
	sheet: Spritesheet;
	animation: BattleRunnerAnimation;
	x: number;
	y: number;
	rowHeightPx: number;
	alpha?: number;
}): AnimatedSprite {
	const { runners, runnerMap, laneId, variantId, sheet, animation, x, y, rowHeightPx, alpha = 1 } = args;
	const textures = runnerAnimationTextures(sheet, animation);
	const anchor = runnerSpriteAnchor(variantId);
	const scale = runnerDisplayScale(rowHeightPx);
	let actor = runnerMap.get(laneId);

	if (!actor || actor.variantId !== variantId) {
		if (actor) actor.sprite.destroy();
		const fallbackTexture = sheet.textures[Object.keys(sheet.textures)[0]];
		const sprite = new AnimatedSprite({
			textures: textures.length ? textures : [fallbackTexture],
			anchor,
			eventMode: "none",
		});
		sprite.cullable = true;
		sprite.scale.set(scale);
		sprite.loop = animation !== "killed" && animation !== "hit";
		runners.addChild(sprite);
		actor = { sprite, variantId, animation };
		runnerMap.set(laneId, actor);
	}

	const sprite = actor.sprite;
	if (actor.animation !== animation) {
		sprite.textures = textures.length ? textures : sprite.textures;
		sprite.loop = animation !== "killed" && animation !== "hit";
		sprite.gotoAndPlay(0);
		actor.animation = animation;
	}
	sprite.animationSpeed = animationSpeedFor(animation);
	if (animation === "killed" || animation === "hit") {
		if (!sprite.playing && sprite.currentFrame >= Math.max(0, textures.length - 1)) {
			sprite.gotoAndStop(Math.max(0, textures.length - 1));
		} else if (!sprite.playing) {
			sprite.gotoAndPlay(0);
		}
	} else if (!sprite.playing) {
		sprite.play();
	}
	sprite.x = Math.round(x);
	sprite.y = Math.round(y);
	sprite.scale.set(scale);
	sprite.alpha = alpha;
	return sprite;
}


function activeKillShotForLane(args: {
	lane: Lane;
	rowY: number;
	currentSeconds: number;
	allottedSeconds: number;
	contentWidth: number;
	useElapsed: boolean;
	allowEvent: (event: LaneEvent) => boolean;
}): KillShotVisual | null {
	let active: KillShotVisual | null = null;
	for (const event of args.lane.events) {
		if (event.kind !== "blue_blast" || !args.allowEvent(event)) continue;
		const shot = killShotVisualForEvent({
			lane: args.lane,
			blastEvent: event,
			rowY: args.rowY,
			currentSeconds: args.currentSeconds,
			allottedSeconds: args.allottedSeconds,
			contentWidth: args.contentWidth,
			useElapsed: args.useElapsed,
		});
		if (shot) active = shot;
	}
	return active;
}

function runnerAnimationForKillShot(
	lane: Lane,
	rowY: number,
	currentSeconds: number,
	allottedSeconds: number,
	contentWidth: number,
	useElapsed: boolean,
	allowEvent: (event: LaneEvent) => boolean,
): BattleRunnerAnimation | null {
	const killShot = activeKillShotForLane({
		lane,
		rowY,
		currentSeconds,
		allottedSeconds,
		contentWidth,
		useElapsed,
		allowEvent,
	});
	if (killShot?.phase === "travel") {
		return lane.parentId ? "walk" : "run";
	}
	if (killShot?.phase === "impact") {
		if (killShot.impactKind === "killed") return "killed";
		if (killShot.impactKind === "blocked") return "blocked";
	}

	for (const event of lane.events) {
		if (event.kind !== "blue_blast" || !event.proven || !allowEvent(event)) continue;
		const blastSeconds = eventElapsedSeconds(event, allottedSeconds, useElapsed);
		const travelEnd = blastSeconds + KILL_SHOT_TRAVEL_SECONDS;
		if (currentSeconds < travelEnd) continue;
		const impactKind = resolveKillShotImpact(lane, event, allottedSeconds, useElapsed);
		if (impactKind !== "killed" && impactKind !== "blocked") continue;
		const terminalEvent = lane.events.find((item) => item.proven && (item.kind === "killed" || item.kind === "blocked"));
		const terminalAt = terminalEvent
			? eventElapsedSeconds(terminalEvent, allottedSeconds, useElapsed)
			: travelEnd + KILL_SHOT_IMPACT_SECONDS;
		if (currentSeconds <= terminalAt + 0.05) {
			return impactKind === "killed" ? "killed" : "blocked";
		}
	}
	return null;
}

export type BattlePixiReplayProbe = {
	killShot: KillShotVisual | null;
	runnerAnimations: Record<string, BattleRunnerAnimation>;
};

export function battlePixiReplayProbe(args: {
	lanes: Lane[];
	rowLayout: BattleRaceEngineRowLayout[];
	fixture: BattleRaceEngineInput["fixture"];
	mode: BattleRaceEngineInput["mode"];
	currentSeconds: number;
	allottedSeconds: number;
	contentWidth: number;
}): BattlePixiReplayProbe {
	const { lanes, rowLayout, fixture, mode, currentSeconds, allottedSeconds, contentWidth } = args;
	const validationGate = pixiReceiptValidationGate(fixture, mode);
	const useElapsed = fixtureUsesElapsedAxis(fixture);
	const allowEvent = (event: LaneEvent) => pixiAllowsTerminalEffect(event, validationGate, mode);
	let killShot: KillShotVisual | null = null;
	const runnerAnimations: Record<string, BattleRunnerAnimation> = {};

	for (const lane of lanes) {
		const row = rowLayout.find((item) => item.laneId === lane.id);
		if (!row) continue;
		const y = row.topPx + row.heightPx / 2;
		const shot = activeKillShotForLane({
			lane,
			rowY: y,
			currentSeconds,
			allottedSeconds,
			contentWidth,
			useElapsed,
			allowEvent,
		});
		if (shot) killShot = shot;
		const killAnimation = runnerAnimationForKillShot(
			lane,
			y,
			currentSeconds,
			allottedSeconds,
			contentWidth,
			useElapsed,
			allowEvent,
		);
		const animation =
			killAnimation ??
			runnerAnimationWithReceiptGate(lane, currentSeconds, allottedSeconds, validationGate.receiptSafe, useElapsed);
		runnerAnimations[lane.id] = animation;
	}
	return { killShot, runnerAnimations };
}

function syncEntities(
	layers: BattlePixiSceneRuntime,
	runnerMap: Map<string, RunnerActor>,
	markerAtlas: Record<string, Texture>,
	lanes: Lane[],
	rowLayout: BattleRaceEngineRowLayout[],
	input: BattleRaceEngineInput,
	contentWidth: number,
	allottedSeconds: number,
	tickerDeltaRatio = 1,
	collapsedParentIds: Set<string> = new Set(),
): { burstFrameIndex: number | null; beatVfx: import("./battle-pixi-beat-vfx").BeatVfxKind } {
	const currentSeconds = input.testMode?.freezeTime ? input.testMode.currentSeconds : input.viewport.currentSeconds;
	layers.onSelectEvent.current = input.onSelectEvent;
	const disableParticles = input.testMode?.disableParticles ?? false;
	const validationGate = pixiReceiptValidationGate(input.fixture, input.mode);
	const useElapsed = fixtureUsesElapsedAxis(input.fixture);
	const spriteTheme = input.fixture.sprite_theme;
	const activeLaneIds = new Set(lanes.map((lane) => lane.id));
	let markerWriteIndex = 0;
	let lucideWriteIndex = 0;

	for (const laneId of [...runnerMap.keys()]) {
		if (!activeLaneIds.has(laneId)) {
			runnerMap.get(laneId)?.sprite.destroy();
			runnerMap.delete(laneId);
		}
	}

	for (const lane of lanes) {
		const row = rowLayout.find((item) => item.laneId === lane.id);
		if (!row) continue;
		let y = Math.round(row.topPx + row.heightPx / 2);
		let runnerX = runnerXAtPlayhead(lane, currentSeconds, allottedSeconds, contentWidth, useElapsed);
		const lineageMotion = childLineageMotion({ lane, lanes, rowLayout, currentSeconds, allottedSeconds, contentWidth, useElapsed });
		if (lineageMotion) {
			runnerX = lineageMotion.x;
			y = lineageMotion.y;
		}

		for (const event of lane.events) {
			const eventSeconds = eventElapsedSeconds(event, allottedSeconds, useElapsed);
			if (eventSeconds > currentSeconds) continue;
			if (event.kind === "useful") continue;
			const mx = secondsToWorldX(eventSeconds, allottedSeconds, contentWidth);
			const marker = battleSpriteTheme.markerForEvent(event);
			if (Math.abs(mx - runnerX) < 16) continue;
			const eventSelection = { eventId: event.id ?? `${lane.id}-${event.kind}-${event.x}`, layers };
			if (hasLucideMarker(event.kind)) {
				// Crisp lucide vector glyph (skull/shield/rocket/…) rendered in-canvas.
				lucideWriteIndex = placePooledLucideMarker(
					layers.lucideMarkerPool,
					layers.markers,
					lucideWriteIndex,
					event.kind,
					mx,
					y,
					marker.opacity ?? 1,
					markerDisplayScale(row.heightPx),
					eventSelection,
				);
			} else {
				markerWriteIndex = placePooledMarker(
					layers.markerPool,
					layers.markers,
					markerWriteIndex,
					textureFromAtlas(marker.texture, markerAtlas),
					mx,
					y,
					marker.opacity ?? 1,
					markerDisplayScale(row.heightPx),
					eventSelection,
				);
			}

			if (event.kind === "blue_blast") continue;

			const effect = battleSpriteTheme.effectForEvent(event);
			if (effect && !disableParticles && effect.texture && pixiAllowsTerminalEffect(event, validationGate, input.mode)) {
				const alpha = Math.max(0.12, 1 - (currentSeconds - eventSeconds) / (effect.durationMs / 1000));
				if (alpha > 0.12) {
					const burstScale = Math.min(1.15, 1 + effect.intensity * 0.2);
					markerWriteIndex = placePooledMarker(
						layers.markerPool,
						layers.markers,
						markerWriteIndex,
						textureFromAtlas(effect.texture, markerAtlas),
						mx,
						y,
						alpha,
						burstScale,
					);
				}
			}
		}

		const variantId = spriteIdForLane(lane, spriteTheme);
		const sheet = runnerSpritesheet(variantId);
		if (!sheet) continue;
		const killShotAnimation = runnerAnimationForKillShot(
			lane,
			y,
			currentSeconds,
			allottedSeconds,
			contentWidth,
			useElapsed,
			(event) => pixiAllowsTerminalEffect(event, validationGate, input.mode),
		);
		const animation =
			killShotAnimation ??
			runnerAnimationWithReceiptGate(lane, currentSeconds, allottedSeconds, validationGate.receiptSafe, useElapsed);
		const activeSegment = activitySegmentAtPlayhead(lane, currentSeconds, allottedSeconds, useElapsed);
		const runnerAlpha = lineageMotion?.alpha ?? (activeSegment?.phase === "authorized_pending" ? 0.42 : activeSegment && isProvisionalSegment(activeSegment) ? 0.62 : 1);
		const renderedRunnerX = clampRunnerX(runnerX, contentWidth, row.heightPx, variantId);
		upsertRunnerActor({
			runners: layers.runners,
			runnerMap,
			laneId: lane.id,
			variantId,
			sheet,
			animation,
			x: renderedRunnerX,
			y,
			rowHeightPx: row.heightPx,
			alpha: runnerAlpha,
		});
	}

	hideUnusedMarkers(layers.markerPool, markerWriteIndex);
	hideUnusedGraphics(layers.lucideMarkerPool, lucideWriteIndex);

	syncBattleEventLabels(layers.eventLabels, lanes, rowLayout, currentSeconds, allottedSeconds, contentWidth, useElapsed);

	syncPixiLineage({
		layer: layers.lineage,
		lanes,
		rowLayout,
		collapsedParentIds,
		allottedSeconds,
		contentWidth,
		useElapsed,
		currentSeconds,
	});

	const beatVfxResult = syncBeatEmphasisVfx({
		layer: layers.beatVfx,
		markerAtlas,
		lanes,
		rowLayout,
		activeBeat: input.activeReceiptBeat,
		currentSeconds,
		allottedSeconds,
		contentWidth,
		useElapsed,
	});

	const killShotResult = syncKillShots({
		layer: layers.killShots,
		markerAtlas,
		lanes,
		rowLayout,
		currentSeconds,
		allottedSeconds,
		contentWidth,
		useElapsed,
		allowEvent: (event) => pixiAllowsTerminalEffect(event, validationGate, input.mode),
		tickerDeltaRatio,
	});

	return { burstFrameIndex: killShotResult.burstFrameIndex, beatVfx: beatVfxResult.vfx };
}

export function renderBattlePixiScene(args: {
	layers: BattlePixiSceneRuntime;
	runnerMap: Map<string, RunnerActor>;
	markerAtlas: Record<string, Texture>;
	lanes: Lane[];
	rowLayout: BattleRaceEngineRowLayout[];
	input: BattleRaceEngineInput;
	contentWidth: number;
	allottedSeconds: number;
	viewportScreenWidth: number;
	viewportScreenHeight: number;
	viewportScrollX: number;
	tickerDeltaRatio?: number;
	collapsedParentIds?: Set<string>;
}): { burstFrameIndex: number | null; beatVfx: import("./battle-pixi-beat-vfx").BeatVfxKind } {
	const { layers, runnerMap, markerAtlas, lanes, rowLayout, input, contentWidth, allottedSeconds, viewportScreenWidth, viewportScreenHeight, viewportScrollX, tickerDeltaRatio = 1, collapsedParentIds = new Set() } = args;
	const currentSeconds = input.testMode?.freezeTime ? input.testMode.currentSeconds : input.viewport.currentSeconds;
	const useElapsed = fixtureUsesElapsedAxis(input.fixture);
	const nextSignature = staticTracksSignature(lanes, rowLayout, allottedSeconds, contentWidth, useElapsed);
	if (nextSignature !== layers.tracksSignature) {
		layers.tracksStatic.cacheAsTexture(false);
		drawStaticTracks(layers.tracksStatic, lanes, rowLayout, allottedSeconds, contentWidth, useElapsed);
		layers.tracksStatic.cacheAsTexture(true);
		layers.tracksSignature = nextSignature;
	}
	drawPlayheadTracks(layers.tracksPlayhead, lanes, rowLayout, allottedSeconds, contentWidth, currentSeconds, useElapsed);
	const syncResult = syncEntities(layers, runnerMap, markerAtlas, lanes, rowLayout, input, contentWidth, allottedSeconds, tickerDeltaRatio, collapsedParentIds);
	updateWorldCullArea(layers.world, viewportScreenWidth, viewportScreenHeight, viewportScrollX);
	return syncResult;
}

export function destroyMarkerPool(pool: Sprite[]) {
	for (const sprite of pool) {
		sprite.destroy();
	}
	pool.length = 0;
}

export function destroyRunnerActors(runners: Map<string, RunnerActor>) {
	for (const actor of runners.values()) {
		actor.sprite.destroy();
	}
	runners.clear();
}

export function teardownBattlePixiSceneLayers(layers: BattlePixiSceneRuntime): void {
	layers.tracksStatic.cacheAsTexture(false);
	destroyMarkerPool(layers.markerPool);
	// Destroy the Graphics wrappers but NOT the shared GraphicsContexts (reused across mounts).
	for (const graphic of layers.lucideMarkerPool) graphic.destroy({ context: false });
	layers.lucideMarkerPool.length = 0;
	teardownBattleEventLabelLayer(layers.eventLabels);
	teardownPixiLineageLayer(layers.lineage);
	teardownKillShotLayer(layers.killShots);
	teardownBeatVfxLayer(layers.beatVfx);
}
