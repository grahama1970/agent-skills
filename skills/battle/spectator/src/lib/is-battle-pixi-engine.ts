/** Phase 1 Pixi spike gate — #battle?engine=pixi */
export function isBattlePixiEngine(): boolean {
	if (typeof window === "undefined") return false;
	const hash = window.location.hash.replace(/^#/, "");
	const [, query = ""] = hash.split("?");
	return new URLSearchParams(query).get("engine") === "pixi";
}

export function battlePixiEngineQuery(): string {
	return isBattlePixiEngine() ? "engine=pixi" : "";
}
