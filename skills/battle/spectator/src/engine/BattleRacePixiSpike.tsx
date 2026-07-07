import { useEffect, useMemo, useRef } from "react";
import { Application } from "pixi.js";
import { Viewport } from "pixi-viewport";
import type { BattleRaceEngineInput, BattleRaceEngineRowLayout, Lane } from "../lib/battle-types";
import { battleRaceAtlasTextures, loadBattleRaceAtlas, unloadBattleRaceAtlas } from "./battle-race-atlas";
import { loadBattleRunnerSprites, unloadBattleRunnerSprites } from "./battle-runner-sprites";
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
	createBattlePixiSceneLayers,
	destroyRunnerActors,
	renderBattlePixiScene,
	teardownBattlePixiSceneLayers,
	type RunnerActor,
} from "./battle-pixi-scene";
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
	playing?: boolean;
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
	playing = false,
}: Props) {
	const hostRef = useRef<HTMLDivElement>(null);
	const runtimeRef = useRef<PixiRaceRuntime | null>(null);
	const runnersRef = useRef<Map<string, RunnerActor>>(new Map());
	const syncingRef = useRef(false);
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
		tick: () => {
			const runtime = runtimeRef.current;
			const state = frameStateRef.current;
			if (!runtime || !state.markerAtlas || !atlasReadyRef.current) return;
			renderBattlePixiScene({
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
			});
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

			const [markerSheet] = await Promise.all([loadBattleRaceAtlas(), loadBattleRunnerSprites(spriteIds)]);
			const markerAtlas = markerSheet.textures;
			if (destroyed) {
				destroyApplication(app);
				return;
			}

			frameStateRef.current.markerAtlas = markerAtlas;
			host.replaceChildren(app.canvas);
			app.canvas.className = "pixiRaceCanvas";
			enableBattlePixiAccessibility(app);

			const viewport = new Viewport({
				events: app.renderer.events,
				screenWidth: Math.max(1, host.clientWidth),
				screenHeight: Math.max(1, totalHeight),
				worldWidth: contentWidth,
				worldHeight: Math.max(1, totalHeight),
			});
			configureBattleViewportAccessibility(viewport);
			app.stage.addChild(viewport);
			viewport.drag({ direction: "x" }).wheel({ smooth: 3 }).decelerate().clamp({ direction: "all" });

			const scene = createBattlePixiSceneLayers();
			viewport.addChild(scene.world);

			viewport.on("moved", () => {
				if (syncingRef.current) return;
				onScrollLeftChange?.(Math.max(0, -viewport.position.x));
			});

			const resizeObserver = new ResizeObserver(() => {
				const runtime = runtimeRef.current;
				if (!runtime) return;
				runtime.viewport.resize(
					Math.max(1, host.clientWidth),
					Math.max(1, totalHeight),
					contentWidth,
					Math.max(1, totalHeight),
				);
			});
			resizeObserver.observe(host);

			const runtime: PixiRaceRuntime = { app, viewport, scene, resizeObserver };
			runtimeRef.current = runtime;
			atlasReadyRef.current = true;
			bindBattlePixiTicker(app, { tick: tickerBindingRef.current.tick, context: tickerBindingRef.current });

			syncingRef.current = true;
			viewport.position.x = -scrollLeft;
			syncingRef.current = false;
			tickerBindingRef.current.tick();
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
			void unloadBattleRaceAtlas();
			void unloadBattleRunnerSprites();
		};
	}, [contentWidth, onScrollLeftChange, scrollLeft, spriteIds, totalHeight]);

	useEffect(() => {
		void loadBattleRunnerSprites(spriteIds);
	}, [spriteIds]);

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
