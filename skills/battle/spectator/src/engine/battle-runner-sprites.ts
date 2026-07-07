import { Assets, Cache, type Spritesheet, type Texture } from "pixi.js";

export const BATTLE_RUNNER_SPRITE_MANIFEST_URL = "/battle-sprites/pixijs/battle-sprite-assets.manifest.json";
export const BATTLE_RUNNER_SPRITE_BASE_URL = "/battle-sprites/pixijs";

export type BattleRunnerSpriteId =
	| "blue_lizard"
	| "green_horn"
	| "nurgling"
	| "purple_horn_imp"
	| "red_human"
	| "skull_horn"
	| "slug_demon"
	| "typhus"
	| "crimson_chainsword_berserker"
	| "crimson_hornbreaker"
	| "crimson_chainsaw_demon"
	| "plague_nurgling";

export type BattleRunnerAnimation =
	| "idle"
	| "walk"
	| "run"
	| "research"
	| "payload"
	| "mutate"
	| "handoff"
	| "spawn"
	| "blocked"
	| "hit"
	| "killed"
	| "victory"
	| "promoted"
	| "fastest_crash";

export type BattleRunnerSpriteManifest = {
	schema: string;
	runtime: string;
	contract: string;
	assets: Array<{
		sprite_id: BattleRunnerSpriteId;
		alias: string;
		json: string;
		png: string;
		frame_width: number;
		frame_height: number;
		columns: number;
		rows: number;
		texture_scale_mode: string;
	}>;
};

export const BATTLE_RUNNER_SPRITE_IDS: BattleRunnerSpriteId[] = [
	"blue_lizard",
	"green_horn",
	"nurgling",
	"purple_horn_imp",
	"red_human",
	"skull_horn",
	"slug_demon",
	"typhus",
	"crimson_chainsword_berserker",
	"crimson_hornbreaker",
	"crimson_chainsaw_demon",
	"plague_nurgling",
];

const RUNNER_ALIAS_PREFIX = "battle-runner-";
const sheets = new Map<BattleRunnerSpriteId, Spritesheet>();
let manifest: BattleRunnerSpriteManifest | null = null;
let loadPromise: Promise<Map<BattleRunnerSpriteId, Spritesheet>> | null = null;
let assetsInit: Promise<void> | null = null;

function runnerAlias(spriteId: BattleRunnerSpriteId): string {
	return `${RUNNER_ALIAS_PREFIX}${spriteId}`;
}

function manifestAsset(spriteId: BattleRunnerSpriteId) {
	if (!manifest) throw new Error("Battle runner sprite manifest not loaded");
	const asset = manifest.assets.find((item) => item.sprite_id === spriteId);
	if (!asset) throw new Error(`Battle runner sprite missing from manifest: ${spriteId}`);
	return asset;
}

function runnerJsonUrl(spriteId: BattleRunnerSpriteId): string {
	const asset = manifestAsset(spriteId);
	return `${BATTLE_RUNNER_SPRITE_BASE_URL}/${asset.json}?v=4`;
}

async function ensureAssetsReady(): Promise<void> {
	if (!assetsInit) assetsInit = Assets.init();
	await assetsInit;
}

function applyNearestNeighbor(sheet: Spritesheet): void {
	for (const texture of Object.values(sheet.textures)) {
		if (texture?.source) texture.source.scaleMode = "nearest";
	}
}

export function runnerSpritesheet(spriteId: BattleRunnerSpriteId): Spritesheet | null {
	return sheets.get(spriteId) ?? null;
}

export function runnerSpriteAnchor(spriteId: BattleRunnerSpriteId): { x: number; y: number } {
	const meta = sheets.get(spriteId)?.data?.meta as { battle?: { anchor?: { x: number; y: number } } } | undefined;
	const battle = meta?.battle;
	return battle?.anchor ?? { x: 0.5, y: 0.85 };
}

export async function loadBattleRunnerSprites(spriteIds: BattleRunnerSpriteId[] = BATTLE_RUNNER_SPRITE_IDS): Promise<Map<BattleRunnerSpriteId, Spritesheet>> {
	const missing = spriteIds.filter((id) => !sheets.has(id));
	if (missing.length === 0) return sheets;

	if (!loadPromise) {
		loadPromise = (async () => {
			await ensureAssetsReady();
			if (!manifest) {
				const response = await fetch(BATTLE_RUNNER_SPRITE_MANIFEST_URL);
				if (!response.ok) throw new Error(`Failed to load battle runner sprite manifest: ${response.status}`);
				manifest = (await response.json()) as BattleRunnerSpriteManifest;
			}

			const targets = spriteIds.length ? spriteIds : manifest.assets.map((asset) => asset.sprite_id);
			await Promise.all(
				targets.map(async (spriteId) => {
					if (sheets.has(spriteId)) return;
					const alias = runnerAlias(spriteId);
					if (!Cache.has(alias)) {
						Assets.add({ alias, src: runnerJsonUrl(spriteId) });
					}
					const sheet = await Assets.load<Spritesheet>(alias);
					if (!sheet?.textures || Object.keys(sheet.textures).length === 0) {
						throw new Error(`Battle runner spritesheet missing frames: ${spriteId}`);
					}
					applyNearestNeighbor(sheet);
					sheets.set(spriteId, sheet);
				}),
			);
			return sheets;
		})().catch((error) => {
			loadPromise = null;
			throw error;
		});
	}

	await loadPromise;
	return sheets;
}

export function runnerAnimationTextures(
	sheet: Spritesheet,
	animation: BattleRunnerAnimation,
): Texture[] {
	const frames = sheet.animations?.[animation];
	return frames?.length ? [...frames] : [];
}

export async function unloadBattleRunnerSprites(): Promise<void> {
	const aliases = [...sheets.keys()].map(runnerAlias);
	sheets.clear();
	manifest = null;
	loadPromise = null;
	await Promise.all(
		aliases.map(async (alias) => {
			if (!Cache.has(alias)) return;
			try {
				await Assets.unload(alias);
			} catch {
				// ignore teardown races
			}
		}),
	);
}
