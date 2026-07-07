import { Container } from "pixi.js";
import { describe, expect, it } from "vitest";
import {
	battlePixiApplicationOptions,
	configureBattleSceneLayer,
	configureBattleViewportAccessibility,
	ensureBattlePixiExtensions,
	updateWorldCullArea,
} from "./battle-pixi-game-mechanics";
import { staticTracksSignature } from "./battle-pixi-scene-signature";

describe("battle pixi game mechanics", () => {
	it("registers battle pixi extensions without throwing", () => {
		expect(() => ensureBattlePixiExtensions()).not.toThrow();
	});

	it("exposes application init defaults required by pixijs-application and pixijs-performance", () => {
		const host = { clientWidth: 640, clientHeight: 240 } as HTMLElement;
		const options = battlePixiApplicationOptions(host);
		expect(options.resizeTo).toBe(host);
		expect(options.antialias).toBe(false);
		expect(options.autoDensity).toBe(true);
		expect(options.gcMaxUnusedTime).toBe(60_000);
	});

	it("configures passive non-interactive scene layers by default", () => {
		const layer = configureBattleSceneLayer(new Container(), { label: "test-layer", cullable: true });
		expect(layer.eventMode).toBe("passive");
		expect(layer.interactiveChildren).toBe(false);
		expect(layer.cullable).toBe(true);
	});

	it("configures accessible viewport shell", () => {
		const viewport = new Container();
		configureBattleViewportAccessibility(viewport);
		expect(viewport.accessible).toBe(true);
		expect(viewport.eventMode).toBe("static");
		expect(viewport.accessibleChildren).toBe(false);
	});

	it("updates world cull bounds from viewport scroll", () => {
		const world = new Container();
		updateWorldCullArea(world, 640, 240, 120);
		expect(world.cullable).toBe(true);
		expect(world.cullArea?.width).toBeGreaterThan(640);
	});
});

describe("staticTracksSignature", () => {
	it("changes when lane timing changes", () => {
		const rowLayout = [{ laneId: "a", topPx: 0, heightPx: 64, isChild: false }];
		const lane = {
			id: "a",
			name: "a",
			payloadId: "a",
			generation: 1,
			team: "red" as const,
			xStart: 0,
			xEnd: 1,
			runnerX: 0,
			runnerState: "advance",
			lineColor: "red" as const,
			terminal: "none" as const,
			events: [],
			activitySegments: [],
		};
		const first = staticTracksSignature([lane], rowLayout, 120, 1000, true);
		const second = staticTracksSignature([{ ...lane, xEnd: 2 }], rowLayout, 120, 1000, true);
		expect(first).not.toBe(second);
	});
});
