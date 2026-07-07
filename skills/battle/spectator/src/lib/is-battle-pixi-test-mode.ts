import type { BattleEngineRenderTestMode } from "./battle-types";

/** Deterministic Pixi screenshot gate — #battle?engine=pixi&pixiTest=1&pixiSeconds=10 */
export function battlePixiTestModeFromUrl(): BattleEngineRenderTestMode | undefined {
	if (typeof window === "undefined") return undefined;
	const hash = window.location.hash.replace(/^#/, "");
	const [, query = ""] = hash.split("?");
	const params = new URLSearchParams(query);
	if (params.get("pixiTest") !== "1" && params.get("renderTest") !== "1") return undefined;

	const rawSeconds = params.get("pixiSeconds") ?? params.get("freezeSeconds") ?? "0";
	const seconds = Number(rawSeconds);
	return {
		freezeTime: true,
		currentSeconds: Number.isFinite(seconds) ? seconds : 0,
		disableParticles: params.get("particles") !== "1",
		deterministicSeed: params.get("seed") ?? "battle-pixi-test",
	};
}
