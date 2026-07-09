import { battleHashSearchParams } from "./battle-receipt-replay";

/** E2E proof hook — #battle/receipt?engine=pixi&hgDeathDemo=1 */
export function battleHungerGamesDeathDemoFromUrl(): boolean {
	if (typeof window === "undefined") return false;
	return battleHashSearchParams(window.location.hash).get("hgDeathDemo") === "1";
}
