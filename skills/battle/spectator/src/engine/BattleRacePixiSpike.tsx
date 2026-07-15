import { useEffect, useMemo, useRef } from "react";
import { Application, type Ticker } from "pixi.js";
import { Viewport } from "pixi-viewport";
import type { BattleRaceEngineInput, BattleRaceEngineRowLayout, Lane } from "../lib/battle-types";
import { battleRaceAtlasTextures, loadBattleRaceAtlas } from "./battle-race-atlas";
import { loadBattleRunnerSprites } from "./battle-runner-sprites";
import { spriteIdForLane } from "./battle-lane-variant-map";
import { PixiHitTargetMirrors } from "./PixiHitTargetMirrors";
import { pixiReceiptValidationGate } from "./battle-pixi-validation";
import {
	battlePixiApplicationOptions,
	bindBattlePixiTicker,
	configureBattleViewportAccessibility,
	enableBattlePixiAccessibility,
	ensureBattlePixiExtensions,
	unbindBattlePixiTicker,
} from "./battle-pixi-game-mechanics";
import {
	battlePixiReplayProbe,
	createBattlePixiSceneLayers,
	destroyRunnerActors,
	renderBattlePixiScene,
	teardownBattlePixiSceneLayers,
	type RunnerActor,
} from "./battle-pixi-scene";
import { lineageTransitionPhase } from "./battle-pixi-lineage";
import "../battle-pixi-engine.css";

type Props = {
	lanes: Lane[];
	rowLayout: BattleRaceEngineRowLayout[];
	input: BattleRaceEngineInput;
	contentWidth: number;
	allottedSeconds: number;
	scrollLeft: number;
	heightPx: number;
	playing?: boolean;
	collapsedParentIds?: Set<string>;
};

type PixiRaceRuntime = {
	app: Application;
	viewport: Viewport;
	scene: ReturnType<typeof createBattlePixiSceneLayers>;
	resizeObserver: ResizeObserver | null;
};

type SceneFrameState = {
	lanes: Lane[];
	rowLayout: BattleRaceEngineRowLayout[];
	input: BattleRaceEngineInput;
	contentWidth: number;
	allottedSeconds: number;
	markerAtlas: Record<string, import("pixi.js").Texture> | null;
	playing: boolean;
};

let pixiMountSequence = 0;

function destroyApplication(app: Application) {
	app.destroy({ removeView: true, releaseGlobalResources: true }, { children: true });
}

function pixiViewportScrollLeft(viewport: Viewport, outerScrollLeft: number, contentWidth: number): number {
	const maxViewportScroll = Math.max(0, contentWidth - viewport.screenWidth);
	return Math.min(maxViewportScroll, Math.max(0, outerScrollLeft));
}

export function BattleRacePixiSpike({
	lanes,
	rowLayout,
	input,
	contentWidth,
	allottedSeconds,
	scrollLeft,
	heightPx,
	playing = false,
	collapsedParentIds = new Set(),
}: Props) {
	const hostRef = useRef<HTMLDivElement>(null);
	const stageHostRef = useRef<HTMLDivElement>(null);
	const runtimeRef = useRef<PixiRaceRuntime | null>(null);
	const runnersRef = useRef<Map<string, RunnerActor>>(new Map());
	const scrollLeftRef = useRef(scrollLeft);
	const contentWidthRef = useRef(contentWidth);
	const totalHeightRef = useRef(0);
	const atlasReadyRef = useRef(false);
	const frameStateRef = useRef<SceneFrameState>({
		lanes,
		rowLayout,
		input,
		contentWidth,
		allottedSeconds,
		markerAtlas: null,
		playing,
	});
	const tickerBindingRef = useRef({
		tick: (ticker: Ticker) => {
			const runtime = runtimeRef.current;
			const state = frameStateRef.current;
			if (!runtime || !state.markerAtlas || !atlasReadyRef.current) return;
			const tickerDeltaRatio = ticker.deltaTime / (1000 / 60);
			let beatVfx: string = "none";
			const syncResult = renderBattlePixiScene({
				layers: runtime.scene,
				runnerMap: runnersRef.current,
				markerAtlas: state.markerAtlas,
				lanes: state.lanes,
				rowLayout: state.rowLayout,
				input: state.input,
				contentWidth: state.contentWidth,
				allottedSeconds: state.allottedSeconds,
				viewportScreenWidth: Math.max(1, runtime.viewport.screenWidth),
				viewportScreenHeight: Math.max(1, runtime.viewport.screenHeight),
				viewportScrollX: Math.max(0, -runtime.viewport.position.x),
				tickerDeltaRatio,
				collapsedParentIds,
			});
			beatVfx = syncResult.beatVfx;
			const probe = battlePixiReplayProbe({
				lanes: state.lanes,
				rowLayout: state.rowLayout,
				fixture: state.input.fixture,
				mode: state.input.mode,
				currentSeconds: state.input.viewport.currentSeconds,
				allottedSeconds: state.allottedSeconds,
				contentWidth: state.contentWidth,
			});
			const stageHost = stageHostRef.current;
			if (stageHost) {
				stageHost.dataset.battleLineagePhases = JSON.stringify(
					Object.fromEntries(state.lanes.filter((lane) => lane.parentId).map((lane) => [lane.id, lineageTransitionPhase(lane, state.input.viewport.currentSeconds)])),
				);
				if (probe.killShot) {
					stageHost.dataset.battleKillShotPhase = probe.killShot.phase;
					stageHost.dataset.battleKillShotImpact = probe.killShot.impactKind;
					stageHost.dataset.battleKillShotLane = probe.killShot.laneId;
					stageHost.dataset.battleKillShotProgress = String(Math.round(probe.killShot.progress * 100));
					if (syncResult.burstFrameIndex != null) {
						stageHost.dataset.battleKillShotBurstFrame = String(syncResult.burstFrameIndex);
					} else {
						delete stageHost.dataset.battleKillShotBurstFrame;
					}
				} else {
					delete stageHost.dataset.battleKillShotPhase;
					delete stageHost.dataset.battleKillShotImpact;
					delete stageHost.dataset.battleKillShotLane;
					delete stageHost.dataset.battleKillShotProgress;
				}
				stageHost.dataset.battleRunnerAnimations = JSON.stringify(probe.runnerAnimations);
				if (state.input.activeReceiptBeat) {
					stageHost.dataset.battleReceiptBeatId = state.input.activeReceiptBeat.id;
					stageHost.dataset.battleReceiptBeatKind = state.input.activeReceiptBeat.kind;
					stageHost.dataset.battleReceiptBeatEmphasis = state.input.activeReceiptBeat.pixi.emphasis;
					stageHost.dataset.battleReceiptBeatVfx = beatVfx;
				} else {
					delete stageHost.dataset.battleReceiptBeatId;
					delete stageHost.dataset.battleReceiptBeatKind;
					delete stageHost.dataset.battleReceiptBeatEmphasis;
					delete stageHost.dataset.battleReceiptBeatVfx;
				}
			}
		},
	});

	const spriteTheme = input.fixture.sprite_theme;
	const spriteIds = useMemo(
		() => [...new Set(lanes.map((lane) => spriteIdForLane(lane, spriteTheme)))],
		[lanes, spriteTheme],
	);
	const validationGate = useMemo(() => pixiReceiptValidationGate(input.fixture, input.mode), [input.fixture, input.mode]);

	const totalHeight = useMemo(
		() => rowLayout.reduce((max, row) => Math.max(max, row.topPx + row.heightPx), 0),
		[rowLayout],
	);
	const initialSpriteIdsRef = useRef(spriteIds);
	totalHeightRef.current = totalHeight;
	contentWidthRef.current = contentWidth;

	useEffect(() => {
		frameStateRef.current = {
			lanes,
			rowLayout,
			input,
			contentWidth,
			allottedSeconds,
			markerAtlas: frameStateRef.current.markerAtlas,
			playing,
		};
	}, [allottedSeconds, contentWidth, input, lanes, playing, rowLayout]);

	useEffect(() => {
		scrollLeftRef.current = scrollLeft;
	}, [scrollLeft]);

	useEffect(() => {
		const host = hostRef.current;
		if (!host) return;

		let destroyed = false;
		ensureBattlePixiExtensions();

		const mount = async () => {
			const app = new Application();
			await app.init(battlePixiApplicationOptions(host));
			if (destroyed) {
				destroyApplication(app);
				return;
			}

			const [markerSheet] = await Promise.all([loadBattleRaceAtlas(), loadBattleRunnerSprites(initialSpriteIdsRef.current)]);
			const markerAtlas = markerSheet.textures;
			if (destroyed) {
				destroyApplication(app);
				return;
			}

			frameStateRef.current.markerAtlas = markerAtlas;
			host.replaceChildren(app.canvas);
			app.canvas.className = "pixiRaceCanvas";
			app.canvas.dataset.battlePixiMountId = String(++pixiMountSequence);
			enableBattlePixiAccessibility(app);

			const viewport = new Viewport({
				events: app.renderer.events,
				screenWidth: Math.max(1, host.clientWidth),
				screenHeight: Math.max(1, totalHeightRef.current),
				worldWidth: contentWidthRef.current,
				worldHeight: Math.max(1, totalHeightRef.current),
			});
			configureBattleViewportAccessibility(viewport);
			app.stage.addChild(viewport);

			const scene = createBattlePixiSceneLayers();
			viewport.addChild(scene.world);

			const resizeObserver = new ResizeObserver(() => {
				const runtime = runtimeRef.current;
				if (!runtime) return;
				runtime.viewport.resize(
					Math.max(1, host.clientWidth),
					Math.max(1, totalHeightRef.current),
					contentWidthRef.current,
					Math.max(1, totalHeightRef.current),
				);
			});
			resizeObserver.observe(host);

			const runtime: PixiRaceRuntime = { app, viewport, scene, resizeObserver };
			runtimeRef.current = runtime;
			atlasReadyRef.current = true;
			bindBattlePixiTicker(app, { tick: tickerBindingRef.current.tick, context: tickerBindingRef.current });

			viewport.position.x = -pixiViewportScrollLeft(viewport, scrollLeftRef.current, contentWidthRef.current);
			tickerBindingRef.current.tick(runtime.app.ticker);
		};

		void mount();

		return () => {
			destroyed = true;
			atlasReadyRef.current = false;
			frameStateRef.current.markerAtlas = null;
			const runtime = runtimeRef.current;
			if (runtime) {
				unbindBattlePixiTicker(runtime.app, { tick: tickerBindingRef.current.tick, context: tickerBindingRef.current });
				runtime.resizeObserver?.disconnect();
				teardownBattlePixiSceneLayers(runtime.scene);
				destroyRunnerActors(runnersRef.current);
				destroyApplication(runtime.app);
				runtimeRef.current = null;
			}
			host.replaceChildren();
		};
	}, []);

	useEffect(() => {
		void loadBattleRunnerSprites(spriteIds);
	}, [spriteIds]);

	useEffect(() => {
		const runtime = runtimeRef.current;
		if (!runtime) return;
		runtime.viewport.resize(
			Math.max(1, hostRef.current?.clientWidth ?? 1),
			Math.max(1, totalHeight),
			contentWidth,
			Math.max(1, totalHeight),
		);
		runtime.viewport.position.x = -pixiViewportScrollLeft(runtime.viewport, scrollLeft, contentWidth);
	}, [contentWidth, scrollLeft, totalHeight]);

	return (
		<div ref={stageHostRef} className="battleRaceStageHost" style={{ height: heightPx }} data-battle-pixi-engine="animated-sprites" data-battle-viewport-seconds={input.viewport.currentSeconds} data-qid="battle:pixi:stage">
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
