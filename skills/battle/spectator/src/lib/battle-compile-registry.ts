import { battleHashPath, battleHashSearchParams } from "./battle-receipt-replay";

export const COMPILE_FIXTURES = {
	"battle-004-pr3d": "/battle-fixtures/battle-004-pr3d-compile/battle.normalized_compile_fixture.json",
} as const;

export type BattleCompileFixtureId = keyof typeof COMPILE_FIXTURES;

export function isBattleCompileView(hash = typeof window !== "undefined" ? window.location.hash : ""): boolean {
	const path = (hash || "").split("?")[0] || battleHashPath();
	return path === "#battle/compile" || path.startsWith("#battle/compile/");
}

export function battleCompileFixtureId(hash = typeof window !== "undefined" ? window.location.hash : ""): BattleCompileFixtureId | null {
	const requested = battleHashSearchParams(hash).get("fixture") ?? "battle-004-pr3d";
	return requested in COMPILE_FIXTURES ? (requested as BattleCompileFixtureId) : null;
}

export function battleCompileFixtureUrl(hash = typeof window !== "undefined" ? window.location.hash : ""): string | null {
	const id = battleCompileFixtureId(hash);
	return id ? COMPILE_FIXTURES[id] : null;
}
