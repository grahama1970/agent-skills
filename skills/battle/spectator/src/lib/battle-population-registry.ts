import { battleHashPath, battleHashSearchParams } from "./battle-receipt-replay";

export const POPULATION_FIXTURES = {
	"battle-004-pr5-population": "/battle-fixtures/battle-004-pr5-population/battle.normalized_population_fixture.json",
} as const;

export type BattlePopulationFixtureId = keyof typeof POPULATION_FIXTURES;

export function isBattlePopulationView(hash = typeof window !== "undefined" ? window.location.hash : ""): boolean {
	const path = (hash || "").split("?")[0] || battleHashPath();
	return path === "#battle/population" || path.startsWith("#battle/population/");
}

export function battlePopulationFixtureId(hash = typeof window !== "undefined" ? window.location.hash : ""): BattlePopulationFixtureId | null {
	const requested = battleHashSearchParams(hash).get("fixture") ?? "battle-004-pr5-population";
	return requested in POPULATION_FIXTURES ? (requested as BattlePopulationFixtureId) : null;
}

export function battlePopulationFixtureUrl(hash = typeof window !== "undefined" ? window.location.hash : ""): string | null {
	const id = battlePopulationFixtureId(hash);
	return id ? POPULATION_FIXTURES[id] : null;
}
