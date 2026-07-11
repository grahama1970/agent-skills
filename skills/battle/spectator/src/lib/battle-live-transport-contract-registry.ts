export const BATTLE_LIVE_TRANSPORT_CONTRACTS = {
	"battle-004": {
		contractUrl: "/battle-fixtures/battle-004-pr8-live-transport/battle.live_transport_contract.json",
		/** Pixi backdrop while live=contract_only — not a live stream claim. */
		companionFixtureUrl: "/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json",
		fileBackedStreamKey: "battle-004-parent-spawn",
	},
} as const;

export type BattleLiveTransportBattleId = keyof typeof BATTLE_LIVE_TRANSPORT_CONTRACTS;

export function isRegisteredLiveTransportBattle(id: string): id is BattleLiveTransportBattleId {
	return id in BATTLE_LIVE_TRANSPORT_CONTRACTS;
}

export function battleLiveTransportContractUrl(battleId: BattleLiveTransportBattleId): string {
	return BATTLE_LIVE_TRANSPORT_CONTRACTS[battleId].contractUrl;
}

export function battleLiveTransportContractCompanionUrl(battleId: BattleLiveTransportBattleId): string {
	return BATTLE_LIVE_TRANSPORT_CONTRACTS[battleId].companionFixtureUrl;
}
