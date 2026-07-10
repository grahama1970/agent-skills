export { BattleSpectatorArena } from "./BattleSpectatorArena";
export { BattleSpectatorRoot, type BattleRegisteredAction } from "./BattleActionRegistrar";
export { BATTLE_SPECTATOR_APP_ID } from "./lib/battle-spectator-app";
export {
	BATTLE_RECEIPT_REPLAY_FIXTURE_URL,
	BATTLE_RECEIPT_REPLAY_FIXTURE_URLS,
	battleReceiptReplayFixtureKey,
	battleReceiptReplayFixtureUrl,
	isBattleReceiptReplayView,
	lanesVisibleAtPlayhead,
	childSpawnElapsedSeconds,
} from "./lib/battle-receipt-replay";
export { isBattlePixiEngine } from "./lib/is-battle-pixi-engine";
export {
	PROOF_CARD_FIXTURES,
	battleProofCardFixtureId,
	battleProofCardFixtureUrl,
	isBattleProofCardView,
} from "./lib/battle-proof-card-registry";
export {
	SYNTHESIS_FIXTURES,
	battleSynthesisFixtureId,
	battleSynthesisFixtureUrl,
	isBattleSynthesisView,
} from "./lib/battle-synthesis-registry";
export { BattleProofCardRoute } from "./proof-card/BattleProofCardRoute";
export { BattleProofCardView } from "./BattleProofCardView";
export { BattleSynthesisRoute } from "./synthesis/BattleSynthesisRoute";
export { BattleComponentCapabilityHarness, isBattleComponentCapabilityTest } from "./BattleComponentCapabilityHarness";
export { BattleComponentIsolationHarness, isBattleComponentIsolationTest } from "./BattleComponentIsolationHarness";

export {
	BATTLE_VIEW_FIXTURE_SCHEMAS,
	type BattleViewFixture,
	type BattleViewKind,
} from "./lib/battle-view-fixture";
export {
	BATTLE_FIXTURE_RENDERERS,
	battleFixtureRegistryEntry,
	isSupportedBattleFixtureSchema,
} from "./lib/battle-view-fixture-registry";
export {
	discriminateBattleViewFixture,
	loadBattleViewFixture,
	loadBattleRaceFixture,
	loadBattleProofCardViewFixture,
	loadBattleSynthesisViewFixture,
} from "./lib/battle-view-fixture-loader";
