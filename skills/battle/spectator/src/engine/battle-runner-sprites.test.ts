import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Regression guard for the loader one-shot bug: a first call that loaded only a
 * subset of sprites must NOT stop a later call from loading the rest. Before the
 * fix a single shared `loadPromise` resolved after the first (partial) set and
 * short-circuited every later call, so lanes whose sheet never loaded rendered
 * nothing (only the G0 seed sprite appeared).
 */

const loadedAliases: string[] = [];

vi.mock("pixi.js", () => {
	const fakeSheet = () => ({ textures: { frame_0: {} }, data: { meta: {} } });
	return {
		Assets: {
			init: vi.fn(async () => undefined),
			load: vi.fn(async (alias: string) => {
				loadedAliases.push(alias);
				return fakeSheet();
			}),
			unload: vi.fn(async () => undefined),
		},
		Cache: { has: () => false },
	};
});

const MANIFEST = {
	schema: "battle.runner_sprite_manifest.v1",
	runtime: "pixijs-v8",
	contract: "test",
	assets: ["plague_nurgling", "crimson_chainsaw_demon", "slug_demon", "typhus"].map((id) => ({
		sprite_id: id,
		alias: `battle-runner-${id}`,
		json: `${id}.json`,
		png: `${id}.png`,
		frame_width: 64,
		frame_height: 64,
		columns: 8,
		rows: 14,
		texture_scale_mode: "nearest",
	})),
};

describe("loadBattleRunnerSprites — incremental loading", () => {
	beforeEach(() => {
		loadedAliases.length = 0;
		vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => MANIFEST })));
	});

	afterEach(async () => {
		const { unloadBattleRunnerSprites } = await import("./battle-runner-sprites");
		await unloadBattleRunnerSprites();
		vi.unstubAllGlobals();
	});

	it("loads sprites requested by a later call even after an earlier partial load", async () => {
		const { loadBattleRunnerSprites } = await import("./battle-runner-sprites");

		const first = await loadBattleRunnerSprites(["plague_nurgling"]);
		expect(first.has("plague_nurgling")).toBe(true);

		const second = await loadBattleRunnerSprites([
			"plague_nurgling",
			"crimson_chainsaw_demon",
			"slug_demon",
			"typhus",
		]);
		// The three new sprites must be present, not skipped by a stale promise.
		expect(second.has("crimson_chainsaw_demon")).toBe(true);
		expect(second.has("slug_demon")).toBe(true);
		expect(second.has("typhus")).toBe(true);
		expect(loadedAliases).toContain("battle-runner-typhus");
	});
});
