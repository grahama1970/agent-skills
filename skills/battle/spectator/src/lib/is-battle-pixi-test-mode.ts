import type { BattleEngineRenderTestMode } from "./battle-types";
import { isBattleCampaignView } from "./battle-campaign-registry";

/** Deterministic Pixi screenshot gate — #battle?engine=pixi&pixiTest=1&pixiSeconds=10 */
export function battlePixiTestModeFromUrl(): BattleEngineRenderTestMode | undefined {
	if (typeof window === "undefined") return undefined;
	const hash = window.location.hash;
	const query = hash.includes("?") ? hash.slice(hash.indexOf("?") + 1) : "";
	const params = new URLSearchParams(query);
	if (params.get("pixiTest") !== "1" && params.get("renderTest") !== "1") return undefined;

	const rawSeconds = params.get("pixiSeconds") ?? params.get("freezeSeconds") ?? "0";
	const seconds = Number(rawSeconds);
	const reducedMotion = params.get("reducedMotion") === "1";
	const campaign = isBattleCampaignView(hash);
	// pixiTest defaults to no particles; campaign route or particles=1 enables them unless reducedMotion/particles=0.
	const particlesExplicitOff = params.get("particles") === "0";
	const particlesExplicitOn = params.get("particles") === "1";
	const disableParticles = reducedMotion || particlesExplicitOff || !(particlesExplicitOn || campaign);

	return {
		freezeTime: true,
		currentSeconds: Number.isFinite(seconds) ? seconds : 0,
		disableParticles,
		deterministicSeed: params.get("seed") ?? "battle-pixi-test",
	};
}
