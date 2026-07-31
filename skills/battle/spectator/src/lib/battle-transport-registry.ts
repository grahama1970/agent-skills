import {
	isRegisteredLiveTransportBattle,
	type BattleLiveTransportBattleId,
} from "./battle-live-transport-contract-registry";

export const BATTLE_LIVE_TRANSPORT_STREAMS = {
	"battle-004-parent-spawn": {
		streamBaseUrl: "/battle-fixtures/battle-004-parent-spawn-pixi-replay/stream",
		companionFixtureUrl: "/battle-fixtures/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json",
		receiptFixtureKey: "battle-004-parent-spawn",
	},
	"battle-004-parent-spawn-lifecycle": {
		streamBaseUrl: "/battle-fixtures/battle-004-parent-spawn-lifecycle-pixi-replay/stream",
		companionFixtureUrl:
			"/battle-fixtures/battle-004-parent-spawn-lifecycle-pixi-replay/battle.normalized_ux_fixture.json",
		receiptFixtureKey: "battle-004-parent-spawn-lifecycle",
	},
	"battle-005-ssrf-metadata": {
		streamBaseUrl: "/battle-fixtures/battle-005-ssrf-metadata-pixi-replay/stream",
		companionFixtureUrl: "/battle-fixtures/battle-005-ssrf-metadata-pixi-replay/battle.normalized_ux_fixture.json",
		receiptFixtureKey: "battle-005-ssrf-metadata",
	},
	"battle-006-pickle-deserialization": {
		streamBaseUrl: "/battle-fixtures/battle-006-pickle-deserialization-pixi-replay/stream",
		companionFixtureUrl:
			"/battle-fixtures/battle-006-pickle-deserialization-pixi-replay/battle.normalized_ux_fixture.json",
		receiptFixtureKey: "battle-006-pickle-deserialization",
	},
	"battle-007-file-upload": {
		streamBaseUrl: "/battle-fixtures/battle-007-file-upload-pixi-replay/stream",
		companionFixtureUrl: "/battle-fixtures/battle-007-file-upload-pixi-replay/battle.normalized_ux_fixture.json",
		receiptFixtureKey: "battle-007-file-upload",
	},
} as const;

export type BattleLiveTransportFixtureKey = keyof typeof BATTLE_LIVE_TRANSPORT_STREAMS;
export type BattleLiveTransportMode = "contract" | "file_backed" | "unsupported";

export function battleHashPath(hash = typeof window !== "undefined" ? window.location.hash : ""): string {
	return hash.split("?")[0] ?? "";
}

export function battleHashSearchParams(hash = typeof window !== "undefined" ? window.location.hash : ""): URLSearchParams {
	const query = hash.includes("?") ? hash.slice(hash.indexOf("?") + 1) : "";
	return new URLSearchParams(query);
}

export function isBattleLiveView(hash = typeof window !== "undefined" ? window.location.hash : ""): boolean {
	const path = battleHashPath(hash);
	return path === "#battle/live" || path.startsWith("#battle/live/");
}

export function isRegisteredLiveTransportFixture(key: string): key is BattleLiveTransportFixtureKey {
	return key in BATTLE_LIVE_TRANSPORT_STREAMS;
}

/** File-backed stream key when ?fixture= is present. No silent default when ?battle= is used. */
export function battleLiveTransportFixtureKey(
	hash = typeof window !== "undefined" ? window.location.hash : "",
): BattleLiveTransportFixtureKey | null {
	const requested = battleHashSearchParams(hash).get("fixture");
	if (!requested) return null;
	return isRegisteredLiveTransportFixture(requested) ? requested : null;
}

/** Contract battle id from ?battle= or default handoff battle-004 when no fixture is requested. */
export function battleLiveTransportBattleId(
	hash = typeof window !== "undefined" ? window.location.hash : "",
): BattleLiveTransportBattleId | null {
	const params = battleHashSearchParams(hash);
	const battle = params.get("battle");
	if (battle) return isRegisteredLiveTransportBattle(battle) ? battle : null;
	if (params.get("fixture")) return null;
	return "battle-004";
}

export function battleLiveTransportMode(
	hash = typeof window !== "undefined" ? window.location.hash : "",
): BattleLiveTransportMode {
	if (battleLiveTransportBattleId(hash)) return "contract";
	if (battleLiveTransportFixtureKey(hash)) return "file_backed";
	return "unsupported";
}

export function battleLiveTransportStreamBaseUrl(hash = typeof window !== "undefined" ? window.location.hash : ""): string | null {
	const key = battleLiveTransportFixtureKey(hash);
	return key ? BATTLE_LIVE_TRANSPORT_STREAMS[key].streamBaseUrl : null;
}

export function battleLiveTransportCompanionFixtureUrl(
	hash = typeof window !== "undefined" ? window.location.hash : "",
): string | null {
	const key = battleLiveTransportFixtureKey(hash);
	return key ? BATTLE_LIVE_TRANSPORT_STREAMS[key].companionFixtureUrl : null;
}
