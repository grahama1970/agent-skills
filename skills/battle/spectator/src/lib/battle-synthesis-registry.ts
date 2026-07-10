import { battleHashPath, battleHashSearchParams } from "./battle-receipt-replay";

export const SYNTHESIS_FIXTURES = {
	"battle-004-pr3c": "/battle-fixtures/battle-004-pr3c-synthesis/battle.normalized_synthesis_fixture.json",
} as const;

export type BattleSynthesisFixtureId = keyof typeof SYNTHESIS_FIXTURES;

export function isBattleSynthesisView(hash = typeof window !== "undefined" ? window.location.hash : ""): boolean {
	const path = (hash || "").split("?")[0] || battleHashPath();
	return path === "#battle/synthesis" || path.startsWith("#battle/synthesis/");
}

export function battleSynthesisFixtureId(hash = typeof window !== "undefined" ? window.location.hash : ""): BattleSynthesisFixtureId | null {
	const requested = battleHashSearchParams(hash).get("fixture") ?? "battle-004-pr3c";
	return requested in SYNTHESIS_FIXTURES ? (requested as BattleSynthesisFixtureId) : null;
}

export function battleSynthesisFixtureUrl(hash = typeof window !== "undefined" ? window.location.hash : ""): string | null {
	const id = battleSynthesisFixtureId(hash);
	return id ? SYNTHESIS_FIXTURES[id] : null;
}
