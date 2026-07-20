import { battleHashPath, battleHashSearchParams } from "./battle-receipt-replay";

export type BattleRaceEngineName = "pixi" | "dom";

/** Resolve renderer from hash: Pixi default on receipt-backed Battle routes; opt out with ?engine=dom */
export function battleRaceEngineFromHash(hash: string): BattleRaceEngineName {
	const engine = battleHashSearchParams(hash).get("engine");
	if (engine === "dom") return "dom";
	if (engine === "pixi") return "pixi";
	const path = hash.split("?")[0];
	if (path === "#battle") return "pixi";
	if (path === "#battle/receipt" || path.startsWith("#battle/receipt/")) return "pixi";
	return "dom";
}

export function battleRaceEngineFromUrl(): BattleRaceEngineName {
	if (typeof window === "undefined") return "dom";
	return battleRaceEngineFromHash(window.location.hash);
}

/** True when Pixi race engine is active (receipt-backed default or explicit ?engine=pixi). */
export function isBattlePixiEngine(): boolean {
	return battleRaceEngineFromUrl() === "pixi";
}

export function battlePixiEngineQuery(): string {
	return isBattlePixiEngine() ? "engine=pixi" : "";
}
