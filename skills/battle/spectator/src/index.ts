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
export {
	COMPILE_FIXTURES,
	battleCompileFixtureId,
	battleCompileFixtureUrl,
	isBattleCompileView,
} from "./lib/battle-compile-registry";
export {
	RUNTIME_FIXTURES,
	battleRuntimeFixtureId,
	battleRuntimeFixtureUrl,
	isBattleRuntimeView,
} from "./lib/battle-runtime-registry";
export {
	POPULATION_FIXTURES,
	battlePopulationFixtureId,
	battlePopulationFixtureUrl,
	isBattlePopulationView,
} from "./lib/battle-population-registry";
export {
	BATTLE_LIVE_TRANSPORT_STREAMS,
	battleLiveTransportFixtureKey,
	battleLiveTransportBattleId,
	battleLiveTransportMode,
	battleLiveTransportStreamBaseUrl,
	battleLiveTransportCompanionFixtureUrl,
	isBattleLiveView,
	isRegisteredLiveTransportFixture,
} from "./lib/battle-transport-registry";
export { loadBattleTransportPackage } from "./lib/battle-transport-loader";
export {
	BATTLE_LIVE_TRANSPORT_CONTRACTS,
	isRegisteredLiveTransportBattle,
} from "./lib/battle-live-transport-contract-registry";
export { loadBattleLiveTransportContract, liveTransportContractViewModel } from "./lib/battle-live-transport-contract-loader";
export { validateLiveTransportContract } from "./lib/battle-live-transport-contract-validator";
export {
	planLiveSseClient,
	shouldOpenEventSource,
	parseSseLiveEventData,
} from "./lib/battle-live-sse-client";
export {
	applyTransportEvent,
	bootstrapTransportState,
	createIdleTransportState,
	recoverTransportFromPackage,
	setTransportFollowLive,
	setTransportCursorSeconds,
	transportViewModel,
} from "./lib/battle-transport-reducer";
export { BattleProofCardRoute } from "./proof-card/BattleProofCardRoute";
export { BattleProofCardView } from "./BattleProofCardView";
export { BattleSynthesisRoute } from "./synthesis/BattleSynthesisRoute";
export { BattleCompileRoute } from "./compile/BattleCompileRoute";
export { BattleRuntimeRoute } from "./runtime/BattleRuntimeRoute";
export { BattlePopulationRoute } from "./population/BattlePopulationRoute";
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
	loadBattleCompileViewFixture,
	loadBattleRuntimeViewFixture,
	loadBattlePopulationViewFixture,
} from "./lib/battle-view-fixture-loader";

export { BattleCampaignStoryPanel } from "./BattleCampaignStoryPanel";
export { buildCampaignStory, campaignChapterAtPlayhead, soundCaptionForCue } from "./lib/battle-campaign-story";
export { isBattleCampaignView, battleCampaignFixtureUrl } from "./lib/battle-campaign-registry";

export { BattleGenesisStoryIntro } from "./BattleGenesisStoryIntro";
export { buildGenesisRoundIntro } from "./lib/battle-genesis-intro";
export { createGenesisMidiPlayer, loadGenesisRoundIntroMidi, parseMidiBytes } from "./lib/battle-genesis-midi";
