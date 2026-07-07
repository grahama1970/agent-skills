import { Assets, Cache, type Spritesheet, type Texture } from "pixi.js";

/**
 * pixijs-assets: spritesheet resolver expects `{name}.{format}.json` (e.g. `.png.json`).
 * @see pixijs-assets/references/spritesheet.md
 */
export const BATTLE_RACE_ATLAS_ALIAS = "battle-race-atlas";
export const BATTLE_RACE_ATLAS_URL = "/battle-race/battle-race-atlas.png.json";

let atlasSheet: Spritesheet | null = null;
let atlasLoad: Promise<Spritesheet> | null = null;
let assetsInit: Promise<void> | null = null;

async function ensureAssetsReady(): Promise<void> {
	if (!assetsInit) assetsInit = Assets.init();
	await assetsInit;
}

export function battleRaceSpritesheet(): Spritesheet | null {
	return atlasSheet;
}

export function battleRaceAtlasTextures(): Record<string, Texture> | null {
	return atlasSheet?.textures ?? null;
}

export async function loadBattleRaceAtlas(): Promise<Spritesheet> {
	if (atlasSheet) return atlasSheet;
	const cached = Assets.get<Spritesheet>(BATTLE_RACE_ATLAS_ALIAS);
	if (cached?.textures && Object.keys(cached.textures).length > 0) {
		atlasSheet = cached;
		return atlasSheet;
	}
	if (!atlasLoad) {
		atlasLoad = (async () => {
			await ensureAssetsReady();
			if (!Cache.has(BATTLE_RACE_ATLAS_ALIAS)) {
				Assets.add({ alias: BATTLE_RACE_ATLAS_ALIAS, src: BATTLE_RACE_ATLAS_URL });
			}
			const sheet = await Assets.load<Spritesheet>(BATTLE_RACE_ATLAS_ALIAS);
			if (!sheet?.textures || Object.keys(sheet.textures).length === 0) {
				throw new Error(`Battle race spritesheet missing frames: ${BATTLE_RACE_ATLAS_URL}`);
			}
			atlasSheet = sheet;
			return atlasSheet;
		})().catch((error) => {
			atlasLoad = null;
			throw error;
		});
	}
	return atlasLoad;
}

export function textureFromAtlas(frame: string | undefined, atlas: Record<string, Texture> | null): Texture | undefined {
	if (!frame || !atlas) return undefined;
	return atlas[frame];
}

/** pixijs-assets/references/caching.md — detach sprites, then Assets.unload */
export async function unloadBattleRaceAtlas(): Promise<void> {
	if (!atlasSheet && !atlasLoad) return;
	if (atlasLoad) {
		try {
			await atlasLoad;
		} catch {
			// load failed
		}
	}
	atlasSheet = null;
	atlasLoad = null;
	if (Cache.has(BATTLE_RACE_ATLAS_ALIAS)) {
		try {
			await Assets.unload(BATTLE_RACE_ATLAS_ALIAS);
		} catch {
			// ignore double-unload / React strict-mode races
		}
	}
}
