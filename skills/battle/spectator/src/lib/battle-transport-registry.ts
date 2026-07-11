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

export function battleLiveTransportFixtureKey(
	hash = typeof window !== "undefined" ? window.location.hash : "",
): BattleLiveTransportFixtureKey | null {
	const requested = battleHashSearchParams(hash).get("fixture") ?? "battle-004-parent-spawn";
	return isRegisteredLiveTransportFixture(requested) ? requested : null;
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

export function isRegisteredLiveTransportFixture(key: string): key is BattleLiveTransportFixtureKey {
	return key in BATTLE_LIVE_TRANSPORT_STREAMS;
}
