import { battleHashPath, battleHashSearchParams } from "./battle-receipt-replay";

export const RUNTIME_FIXTURES = {
	"battle-004-pr4": "/battle-fixtures/battle-004-pr4-runtime-judge/battle.normalized_runtime_judge_fixture.json",
} as const;

export type BattleRuntimeFixtureId = keyof typeof RUNTIME_FIXTURES;

export function isBattleRuntimeView(hash = typeof window !== "undefined" ? window.location.hash : ""): boolean {
	const path = (hash || "").split("?")[0] || battleHashPath();
	return path === "#battle/runtime" || path.startsWith("#battle/runtime/");
}

export function battleRuntimeFixtureId(hash = typeof window !== "undefined" ? window.location.hash : ""): BattleRuntimeFixtureId | null {
	const requested = battleHashSearchParams(hash).get("fixture") ?? "battle-004-pr4";
	return requested in RUNTIME_FIXTURES ? (requested as BattleRuntimeFixtureId) : null;
}

export function battleRuntimeFixtureUrl(hash = typeof window !== "undefined" ? window.location.hash : ""): string | null {
	const id = battleRuntimeFixtureId(hash);
	return id ? RUNTIME_FIXTURES[id] : null;
}
