import { useEffect, useMemo, useRef } from "react";
import { AnimatedSprite, Application, Container, Graphics, Sprite, type Spritesheet, type Texture } from "pixi.js";
import { Viewport } from "pixi-viewport";
import type { BattleRaceEngineInput, BattleRaceEngineRowLayout, Lane, LaneActivitySegment } from "../lib/battle-types";
import { battleRaceAtlasTextures, loadBattleRaceAtlas, textureFromAtlas, unloadBattleRaceAtlas } from "./battle-race-atlas";
import { loadBattleRunnerSprites, runnerAnimationTextures, runnerSpriteAnchor, runnerSpritesheet, unloadBattleRunnerSprites, type BattleRunnerAnimation, type BattleRunnerSpriteId } from "./battle-runner-sprites";
import {
	activitySegmentAtPlayhead,
	animationSpeedFor,
	isProvisionalSegment,
	runnerAnimationWithReceiptGate,
} from "./battle-runner-animation";
import { spriteVariantForLane } from "./battle-lane-variant-map";
import { battleSpriteTheme } from "./battle-sprite-theme";
import { PixiHitTargetMirrors } from "./PixiHitTargetMirrors";
import { pixiAllowsTerminalEffect, pixiReceiptValidationGate } from "./battle-pixi-validation";
import {
	eventElapsedSeconds,
	fixtureUsesElapsedAxis,
	laneElapsedRange,
	segmentElapsedRange,
} from "../lib/battle-elapsed-axis";
import "../battle-pixi-engine.css";

type Props = {
	lanes: Lane[];
	rowLayout: BattleRaceEngineRowLayout[];
	input: BattleRaceEngineInput;
	contentWidth: number;
	allottedSeconds: number;
	scrollLeft: number;
	onScrollLeftChange?: (scrollLeft: number) => void;
	heightPx: number;
};

type PixiRaceRuntime = {
	app: Application;
	viewport: Viewport;
	tracks: Graphics;
	markers: Container;
	runners: Container;
};

type RunnerActor = {
	sprite: AnimatedSprite;
	variantId: BattleRunnerSpriteId;
	animation: BattleRunnerAnimation;
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

function placeSprite(container: Container, texture: Texture | undefined, x: number, y: number, alpha: number, scale = 1) {
	if (!texture) return;
	const sprite = new Sprite({
		texture,
		anchor: 0.5,
		x,
		y,
		alpha,
		scale,
	});
	container.addChild(sprite);
}

function destroyRunnerActors(runners: Map<string, RunnerActor>) {
	for (const actor of runners.values()) {
		actor.sprite.destroy();
	}
	runners.clear();
}

function clearMarkers(markers: Container) {
	for (const child of markers.removeChildren()) {
		child.destroy();
	}
}

function clearRunners(runners: Map<string, RunnerActor>) {
	destroyRunnerActors(runners);
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
	const scale = Math.max(1.0, Math.min(1.8, (rowHeightPx * 0.95) / 64));
	let actor = runnerMap.get(laneId);

	if (!actor || actor.variantId !== variantId) {
		if (actor) actor.sprite.destroy();
		const sprite = new AnimatedSprite(textures.length ? textures : [sheet.textures[Object.keys(sheet.textures)[0]]]);
		sprite.anchor.set(anchor.x, anchor.y);
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
	if (!sprite.playing) sprite.play();
	sprite.x = x;
	sprite.y = y;
	sprite.scale.set(scale);
	sprite.alpha = alpha;
	return sprite;
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

function drawTracks(
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

function syncEntities(
	markers: Container,
	runners: Container,
	runnerMap: Map<string, RunnerActor>,
	markerAtlas: Record<string, Texture>,
	lanes: Lane[],
	rowLayout: BattleRaceEngineRowLayout[],
	input: BattleRaceEngineInput,
	contentWidth: number,
	allottedSeconds: number,
) {
	const currentSeconds = input.testMode?.freezeTime ? input.testMode.currentSeconds : input.viewport.currentSeconds;
	const disableParticles = input.testMode?.disableParticles ?? false;
	const validationGate = pixiReceiptValidationGate(input.fixture, input.mode);
	const useElapsed = fixtureUsesElapsedAxis(input.fixture);
	const activeLaneIds = new Set(lanes.map((lane) => lane.id));

	clearMarkers(markers);

	for (const laneId of [...runnerMap.keys()]) {
		if (!activeLaneIds.has(laneId)) {
			runnerMap.get(laneId)?.sprite.destroy();
			runnerMap.delete(laneId);
		}
	}

	const runnerJobs: Array<{
		lane: Lane;
		row: BattleRaceEngineRowLayout;
		runnerX: number;
		y: number;
	}> = [];

	for (const lane of lanes) {
		const row = rowLayout.find((item) => item.laneId === lane.id);
		if (!row) continue;
		const y = row.topPx + row.heightPx / 2;
		const runnerX = runnerXAtPlayhead(lane, currentSeconds, allottedSeconds, contentWidth, useElapsed);
		runnerJobs.push({ lane, row, runnerX, y });

		for (const event of lane.events) {
			const eventSeconds = eventElapsedSeconds(event, allottedSeconds, useElapsed);
			if (eventSeconds > currentSeconds) continue;
			const mx = secondsToWorldX(eventSeconds, allottedSeconds, contentWidth);
			const marker = battleSpriteTheme.markerForEvent(event);
			placeSprite(markers, textureFromAtlas(marker.texture, markerAtlas), mx, y, marker.opacity ?? 1);

			const effect = battleSpriteTheme.effectForEvent(event);
			if (!effect || disableParticles || !effect.texture) continue;
			if (!pixiAllowsTerminalEffect(event, validationGate, input.mode)) continue;
			const alpha = Math.max(0.12, 1 - (currentSeconds - eventSeconds) / (effect.durationMs / 1000));
			if (alpha <= 0.12) continue;
			const burstScale = 1 + effect.intensity * 0.35;
			placeSprite(markers, textureFromAtlas(effect.texture, markerAtlas), mx, y, alpha, burstScale);
		}
	}

	for (const job of runnerJobs) {
		const variantId = spriteVariantForLane(job.lane);
		const sheet = runnerSpritesheet(variantId);
		if (!sheet) continue;
		const animation = runnerAnimationWithReceiptGate(job.lane, currentSeconds, allottedSeconds, validationGate.receiptSafe, useElapsed);
		const activeSegment = activitySegmentAtPlayhead(job.lane, currentSeconds, allottedSeconds, useElapsed);
		const runnerAlpha = activeSegment && isProvisionalSegment(activeSegment) ? 0.62 : 1;
		upsertRunnerActor({
			runners,
			runnerMap,
			laneId: job.lane.id,
			variantId,
			sheet,
			animation,
			x: job.runnerX,
			y: job.y,
			rowHeightPx: job.row.heightPx,
			alpha: runnerAlpha,
		});
	}
}

function renderScene(
	runtime: PixiRaceRuntime,
	runnerMap: Map<string, RunnerActor>,
	markerAtlas: Record<string, Texture>,
	lanes: Lane[],
	rowLayout: BattleRaceEngineRowLayout[],
	input: BattleRaceEngineInput,
	contentWidth: number,
	allottedSeconds: number,
) {
	const currentSeconds = input.testMode?.freezeTime ? input.testMode.currentSeconds : input.viewport.currentSeconds;
	const useElapsed = fixtureUsesElapsedAxis(input.fixture);
	drawTracks(runtime.tracks, lanes, rowLayout, allottedSeconds, contentWidth, currentSeconds, useElapsed);
	syncEntities(runtime.markers, runtime.runners, runnerMap, markerAtlas, lanes, rowLayout, input, contentWidth, allottedSeconds);
}

function destroyApplication(app: Application) {
	app.destroy({ removeView: true, releaseGlobalResources: true }, { children: true });
}

export function BattleRacePixiSpike({
	lanes,
	rowLayout,
	input,
	contentWidth,
	allottedSeconds,
	scrollLeft,
	onScrollLeftChange,
	heightPx,
}: Props) {
	const hostRef = useRef<HTMLDivElement>(null);
	const runtimeRef = useRef<PixiRaceRuntime | null>(null);
	const runnersRef = useRef<Map<string, RunnerActor>>(new Map());
	const syncingRef = useRef(false);
	const atlasReadyRef = useRef(false);

	const spriteIds = useMemo(() => [...new Set(lanes.map(spriteVariantForLane))], [lanes]);
	const validationGate = useMemo(() => pixiReceiptValidationGate(input.fixture, input.mode), [input.fixture, input.mode]);

	const totalHeight = useMemo(
		() => rowLayout.reduce((max, row) => Math.max(max, row.topPx + row.heightPx), 0),
		[rowLayout],
	);

	useEffect(() => {
		const host = hostRef.current;
		if (!host) return;

		let destroyed = false;

		const mount = async () => {
			const app = new Application();
			await app.init({
				width: Math.max(1, host.clientWidth),
				height: Math.max(1, totalHeight),
				backgroundAlpha: 0,
				antialias: false,
				resolution: window.devicePixelRatio || 1,
				autoDensity: true,
			});
			if (destroyed) {
				destroyApplication(app);
				return;
			}

			const [markerSheet] = await Promise.all([loadBattleRaceAtlas(), loadBattleRunnerSprites(spriteIds)]);
			const markerAtlas = markerSheet.textures;
			if (destroyed) {
				destroyApplication(app);
				return;
			}

			host.replaceChildren(app.canvas);
			app.canvas.className = "pixiRaceCanvas";

			const viewport = new Viewport({
				events: app.renderer.events,
				screenWidth: Math.max(1, host.clientWidth),
				screenHeight: Math.max(1, totalHeight),
				worldWidth: contentWidth,
				worldHeight: Math.max(1, totalHeight),
			});
			app.stage.addChild(viewport);
			viewport.drag({ direction: "x" }).wheel({ smooth: 3 }).decelerate().clamp({ direction: "all" });

			const world = new Container();
			viewport.addChild(world);
			const tracks = new Graphics();
			const markers = new Container();
			const runners = new Container();
			world.addChild(tracks);
			world.addChild(markers);
			world.addChild(runners);

			viewport.on("moved", () => {
				if (syncingRef.current) return;
				onScrollLeftChange?.(Math.max(0, -viewport.position.x));
			});

			const runtime = { app, viewport, tracks, markers, runners };
			runtimeRef.current = runtime;
			atlasReadyRef.current = true;
			renderScene(runtime, runnersRef.current, markerAtlas, lanes, rowLayout, input, contentWidth, allottedSeconds);
			syncingRef.current = true;
			viewport.position.x = -scrollLeft;
			syncingRef.current = false;
		};

		void mount();

		return () => {
			destroyed = true;
			atlasReadyRef.current = false;
			const runtime = runtimeRef.current;
			if (runtime) {
				clearMarkers(runtime.markers);
				clearRunners(runnersRef.current);
				destroyApplication(runtime.app);
				runtimeRef.current = null;
			}
			host.replaceChildren();
			void unloadBattleRaceAtlas();
			void unloadBattleRunnerSprites();
		};
	}, [allottedSeconds, contentWidth, onScrollLeftChange, spriteIds, totalHeight]);

	useEffect(() => {
		void loadBattleRunnerSprites(spriteIds);
	}, [spriteIds]);

	useEffect(() => {
		const runtime = runtimeRef.current;
		const markerAtlas = battleRaceAtlasTextures();
		if (!runtime || !markerAtlas || !atlasReadyRef.current) return;
		renderScene(runtime, runnersRef.current, markerAtlas, lanes, rowLayout, input, contentWidth, allottedSeconds);
	}, [allottedSeconds, contentWidth, input, lanes, rowLayout]);

	useEffect(() => {
		const runtime = runtimeRef.current;
		if (!runtime) return;
		syncingRef.current = true;
		runtime.viewport.position.x = -scrollLeft;
		syncingRef.current = false;
	}, [scrollLeft]);

	return (
		<div className="battleRaceStageHost" style={{ height: heightPx }} data-battle-pixi-engine="animated-sprites" data-battle-viewport-seconds={input.viewport.currentSeconds}>
			{validationGate.warning ? (
				<div className="battlePixiValidationWarning" role="status" data-qid="battle:pixi:validation-warning">
					{validationGate.warning}
				</div>
			) : null}
			<div ref={hostRef} className="battleRaceTrackPlane" />
			<PixiHitTargetMirrors
				lanes={lanes}
				rowLayout={rowLayout}
				input={input}
				contentWidth={contentWidth}
				allottedSeconds={allottedSeconds}
				scrollLeft={scrollLeft}
			/>
		</div>
	);
}
