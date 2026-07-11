import { battleHashPath, battleHashSearchParams } from "./battle-receipt-replay";

export const MUSIC_FIXTURES = {
	"battle-004-music-runtime": "/battle-fixtures/battle-004-music-runtime/battle.normalized_music_fixture.json",
} as const;

export type BattleMusicFixtureId = keyof typeof MUSIC_FIXTURES;

export function isBattleMusicView(hash = typeof window !== "undefined" ? window.location.hash : ""): boolean {
	const path = (hash || "").split("?")[0] || battleHashPath();
	return path === "#battle/music" || path.startsWith("#battle/music/");
}

export function battleMusicFixtureId(
	hash = typeof window !== "undefined" ? window.location.hash : "",
): BattleMusicFixtureId | null {
	const requested = battleHashSearchParams(hash).get("fixture") ?? "battle-004-music-runtime";
	return requested in MUSIC_FIXTURES ? (requested as BattleMusicFixtureId) : null;
}

export function battleMusicFixtureUrl(
	hash = typeof window !== "undefined" ? window.location.hash : "",
): string | null {
	const id = battleMusicFixtureId(hash);
	return id ? MUSIC_FIXTURES[id] : null;
}
