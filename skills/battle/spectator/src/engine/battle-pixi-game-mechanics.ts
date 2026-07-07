import {
	Application,
	Container,
	CullerPlugin,
	Rectangle,
	Ticker,
	UPDATE_PRIORITY,
	extensions,
	type ApplicationOptions,
} from "pixi.js";

let battlePixiExtensionsReady = false;

/** pixijs-performance — register CullerPlugin before Application.init */
export function ensureBattlePixiExtensions(): void {
	if (battlePixiExtensionsReady) return;
	extensions.add(CullerPlugin);
	battlePixiExtensionsReady = true;
}

export type BattlePixiInitOptions = {
	resizeTo: HTMLElement;
};

/** pixijs-application + pixijs-performance init defaults for battle spectator */
export function battlePixiApplicationOptions(host: HTMLElement): ApplicationOptions {
	return {
		resizeTo: host,
		backgroundAlpha: 0,
		antialias: false,
		resolution: (typeof window !== "undefined" ? window.devicePixelRatio : 1) || 1,
		autoDensity: true,
		gcMaxUnusedTime: 60_000,
		gcFrequency: 30_000,
	} as ApplicationOptions;
}

export type BattleSceneLayerOptions = {
	label: string;
	cullable?: boolean;
	interactive?: boolean;
};

/** pixijs-events + pixijs-scene-container defaults for non-interactive render layers */
export function configureBattleSceneLayer(container: Container, options: BattleSceneLayerOptions): Container {
	container.label = options.label;
	container.eventMode = options.interactive ? "static" : "passive";
	container.interactiveChildren = options.interactive ?? false;
	if (options.cullable !== undefined) container.cullable = options.cullable;
	return container;
}

/** pixijs-accessibility — keyboard-discoverable viewport shell (DOM mirrors remain primary selectors) */
export function configureBattleViewportAccessibility(container: Container): void {
	container.accessible = true;
	container.accessibleTitle = "Battle receipt replay viewport";
	container.accessibleHint = "Drag horizontally to pan the timeline. Lane and event selection uses the overlay controls.";
	container.accessibleType = "div";
	container.eventMode = "static";
	container.accessibleChildren = false;
	container.tabIndex = 0;
}

export function updateWorldCullArea(world: Container, viewportScreenWidth: number, viewportScreenHeight: number, scrollX: number): void {
	const pad = 96;
	const cullArea = new Rectangle(scrollX - pad, -pad, viewportScreenWidth + pad * 2, viewportScreenHeight + pad * 2);
	world.cullable = true;
	world.cullArea = cullArea;
}

export type BattlePixiTickerBinding = {
	tick: (ticker: Ticker) => void;
	context: object;
};

/** pixijs-ticker — frame loop with explicit priority and teardown-safe binding */
export function bindBattlePixiTicker(app: Application, binding: BattlePixiTickerBinding): void {
	app.ticker.add(binding.tick, binding.context, UPDATE_PRIORITY.LOW);
}

export function unbindBattlePixiTicker(app: Application, binding: BattlePixiTickerBinding): void {
	app.ticker.remove(binding.tick, binding.context);
}

export function enableBattlePixiAccessibility(app: Application): void {
	app.renderer.accessibility.setAccessibilityEnabled(true);
}
