/** Compatibility barrel for the thin UX1 slice. Prefer battle-proof-card-registry / view-model. */
export {
	PROOF_CARD_FIXTURES as BATTLE_PROOF_CARD_FIXTURE_URLS,
	battleProofCardFixtureId,
	battleProofCardFixtureUrl,
	isBattleProofCardView,
	type BattleProofCardFixtureId as BattleProofCardKind,
} from "./battle-proof-card-registry";
export type { BattleNormalizedProofCardFixtureV1 as BattleNormalizedProofCardFixture } from "./battle-proof-card-types";
export { humanizeProofClaimKey, buildProofCardViewModel, proofCardNodeRowsCompat as proofCardNodeRows } from "./battle-proof-card-compat";
export { proofCardContainsForbiddenClaim, proofCardForbiddenClaimPhrases } from "./battle-proof-card-compat";
