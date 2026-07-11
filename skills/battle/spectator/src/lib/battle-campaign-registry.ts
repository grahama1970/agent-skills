import { battleHashPath, battleHashSearchParams } from "./battle-receipt-replay";
import {
	BATTLE_RECEIPT_REPLAY_FIXTURE_URLS,
	type BattleReceiptReplayFixtureKey,
} from "./battle-receipt-replay";

export const BATTLE_CAMPAIGN_DEFAULT_FIXTURE: BattleReceiptReplayFixtureKey = "battle-004-pr6-genetic-pixi";

export function isBattleCampaignView(hash = typeof window !== "undefined" ? window.location.hash : ""): boolean {
	const path = (hash || "").split("?")[0] || battleHashPath();
	return path === "#battle/campaign" || path.startsWith("#battle/campaign/");
}

/** Campaign storytelling uses the genetic Pixi fixture by default. */
export function battleCampaignFixtureKey(
	hash = typeof window !== "undefined" ? window.location.hash : "",
): BattleReceiptReplayFixtureKey {
	const requested = battleHashSearchParams(hash).get("fixture") ?? BATTLE_CAMPAIGN_DEFAULT_FIXTURE;
	return requested in BATTLE_RECEIPT_REPLAY_FIXTURE_URLS
		? (requested as BattleReceiptReplayFixtureKey)
		: BATTLE_CAMPAIGN_DEFAULT_FIXTURE;
}

export function battleCampaignFixtureUrl(
	hash = typeof window !== "undefined" ? window.location.hash : "",
): string {
	return BATTLE_RECEIPT_REPLAY_FIXTURE_URLS[battleCampaignFixtureKey(hash)];
}

export function battleCampaignPresentationFromUrl(
	hash = typeof window !== "undefined" ? window.location.hash : "",
): {
	reducedMotion: boolean;
	particles: boolean;
	mute: boolean;
} {
	const params = battleHashSearchParams(hash);
	const reducedMotion =
		params.get("reducedMotion") === "1" ||
		(typeof window !== "undefined" &&
			typeof window.matchMedia === "function" &&
			window.matchMedia("(prefers-reduced-motion: reduce)").matches);
	const mute = params.get("mute") === "1";
	const particles = !reducedMotion && params.get("particles") !== "0";
	const skipIntro = params.get("skipIntro") === "1";
	return { reducedMotion, particles, mute, skipIntro };
}
