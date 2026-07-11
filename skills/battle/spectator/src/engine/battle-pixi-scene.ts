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
import { createPixiLineageLayer, syncPixiLineage, teardownPixiLineageLayer, type PixiLineageLayer } from "./battle-pixi-lineage";
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
	markerPool: Sprite[];
};

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
	const world = configureBattleSceneLayer(new Container(), { label: "battle-world", cullable: true });
	const tracksStatic = new Graphics();
	const tracksPlayhead = new Graphics();
	configureBattleSceneLayer(tracksStatic, { label: "battle-tracks-static", cullable: true });
	configureBattleSceneLayer(tracksPlayhead, { label: "battle-tracks-playhead", cullable: true });
	const markers = configureBattleSceneLayer(new Container(), { label: "battle-markers", cullable: true });
	const lineage = createPixiLineageLayer();
	const killShots = createKillShotLayer();
	const beatVfx = createBeatVfxLayer();
	const runners = configureBattleSceneLayer(new Container(), { label: "battle-runners", cullable: true });
	world.addChild(tracksStatic);
	world.addChild(tracksPlayhead);
	world.addChild(markers);
	world.addChild(lineage.container);
	world.addChild(killShots.container);
	world.addChild(beatVfx.container);
	world.addChild(runners);
	return { world, tracksStatic, tracksPlayhead, markers, lineage, killShots, beatVfx, runners, markerPool: [], tracksSignature: "" };
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
		const y = row.topPx + row.heightPx / 2;
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
		const y = row.topPx + row.heightPx / 2;
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
	graphics.setStrokeStyle({ width: 2, color: 0x22d3ee, alpha: 0.95 });
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
): number {
	if (!texture) return writeIndex;
	let sprite = pool[writeIndex];
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
	return writeIndex + 1;
}

function hideUnusedMarkers(pool: Sprite[], usedCount: number) {
	for (let index = usedCount; index < pool.length; index += 1) {
		pool[index].visible = false;
	}
}


/** Readable in-lane runners — match design row band without 95% pile-up. */
export function runnerDisplayScale(rowHeightPx: number): number {
	const framePx = 64;
	const raw = (Math.max(24, rowHeightPx) * 0.78) / framePx;
	return Math.max(0.65, Math.min(1.15, raw));
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
	const disableParticles = input.testMode?.disableParticles ?? false;
	const validationGate = pixiReceiptValidationGate(input.fixture, input.mode);
	const useElapsed = fixtureUsesElapsedAxis(input.fixture);
	const spriteTheme = input.fixture.sprite_theme;
	const activeLaneIds = new Set(lanes.map((lane) => lane.id));
	let markerWriteIndex = 0;

	for (const laneId of [...runnerMap.keys()]) {
		if (!activeLaneIds.has(laneId)) {
			runnerMap.get(laneId)?.sprite.destroy();
			runnerMap.delete(laneId);
		}
	}

	for (const lane of lanes) {
		const row = rowLayout.find((item) => item.laneId === lane.id);
		if (!row) continue;
		const y = row.topPx + row.heightPx / 2;
		const runnerX = runnerXAtPlayhead(lane, currentSeconds, allottedSeconds, contentWidth, useElapsed);

		for (const event of lane.events) {
			const eventSeconds = eventElapsedSeconds(event, allottedSeconds, useElapsed);
			if (eventSeconds > currentSeconds) continue;
			const mx = secondsToWorldX(eventSeconds, allottedSeconds, contentWidth);
			const marker = battleSpriteTheme.markerForEvent(event);
			if (Math.abs(mx - runnerX) < 16) continue;
			markerWriteIndex = placePooledMarker(
				layers.markerPool,
				layers.markers,
				markerWriteIndex,
				textureFromAtlas(marker.texture, markerAtlas),
				mx,
				y,
				marker.opacity ?? 1,
			);

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
		const runnerAlpha = activeSegment && isProvisionalSegment(activeSegment) ? 0.62 : 1;
		upsertRunnerActor({
			runners: layers.runners,
			runnerMap,
			laneId: lane.id,
			variantId,
			sheet,
			animation,
			x: runnerX,
			y,
			rowHeightPx: row.heightPx,
			alpha: runnerAlpha,
		});
	}

	hideUnusedMarkers(layers.markerPool, markerWriteIndex);

	syncPixiLineage({
		layer: layers.lineage,
		lanes,
		rowLayout,
		collapsedParentIds,
		allottedSeconds,
		contentWidth,
		useElapsed,
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
	teardownPixiLineageLayer(layers.lineage);
	teardownKillShotLayer(layers.killShots);
	teardownBeatVfxLayer(layers.beatVfx);
}
